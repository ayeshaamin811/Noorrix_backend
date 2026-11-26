from django import forms
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.utils.html import format_html, format_html_join

from .models import Car, CarFeature, CarImage, Colour, Favourite, FeatureCategory
from .utils import to_browser_safe_image

FEATURE_BULK_FIELDS = {
    "exterior_features":     FeatureCategory.EXTERIOR,
    "interior_features":     FeatureCategory.INTERIOR,
    "performance_features":  FeatureCategory.PERFORMANCE,
    "size_features":         FeatureCategory.SIZE_AND_DIMENSIONS,
    "audio_features":        FeatureCategory.AUDIO_AND_COMMUNICATIONS,
}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A FileField that accepts and validates a list of uploaded files."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            return [super(MultipleFileField, self).clean(d, initial) for d in data]
        return super().clean(data, initial)


class SuggestionTextInput(forms.TextInput):
    """A text box that suggests values from a list but accepts anything typed."""

    def __init__(self, suggestions=(), attrs=None):
        super().__init__(attrs)
        self.suggestions = list(suggestions)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        list_id = f"{attrs.get('id', name)}_suggestions"
        attrs.update(list=list_id, autocomplete="off")
        options = format_html_join("", '<option value="{}">', ((s,) for s in self.suggestions))
        return format_html(
            '{}<datalist id="{}">{}</datalist>',
            super().render(name, value, attrs, renderer), list_id, options,
        )


def colour_suggestions():
    """The standard colours plus any typed in for earlier cars, so spellings stay the same."""
    used = Car.objects.exclude(colour="").order_by().values_list("colour", flat=True).distinct()
    by_key = {colour.casefold(): colour for colour in used}
    by_key.update({colour.casefold(): colour for colour in Colour.values})
    return sorted(by_key.values())


class CarAdminForm(forms.ModelForm):
    gallery_images = MultipleFileField(
        required=False,
        help_text="Select all gallery images at once (e.g. 50-100 files) — added after Save.",
    )
    exterior_features = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 5}),
        label="Exterior features", help_text="One feature per line — replaces this category's list on Save.",
    )
    interior_features = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 5}),
        label="Interior features", help_text="One feature per line — replaces this category's list on Save.",
    )
    performance_features = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 5}),
        label="Performance features", help_text="One feature per line — replaces this category's list on Save.",
    )
    size_features = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 5}),
        label="Size and dimensions", help_text="One item per line — replaces this category's list on Save.",
    )
    audio_features = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 5}),
        label="Audio and Communications features", help_text="One feature per line — replaces this category's list on Save.",
    )

    class Meta:
        model = Car
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.colour_suggestions = colour_suggestions()
        colour_field = self.fields["colour"]
        colour_field.widget = SuggestionTextInput(self.colour_suggestions, attrs=colour_field.widget.attrs)
        if self.instance and self.instance.pk:
            for field_name, category in FEATURE_BULK_FIELDS.items():
                texts = self.instance.features.filter(category=category).values_list("text", flat=True)
                self.fields[field_name].initial = "\n".join(texts)

    def clean_colour(self):
        """Tidy the spacing, and use the existing spelling, so "black" saves as "Black"."""
        colour = " ".join((self.cleaned_data.get("colour") or "").split())
        for known in self.colour_suggestions:
            if known.casefold() == colour.casefold():
                return known
        return colour

    def clean_image(self):
        image = self.cleaned_data.get("image")
        # Only a freshly uploaded file needs processing — an unchanged value is
        # the existing (already-committed) FieldFile, re-processing it on every
        # save is wasteful and breaks if the underlying file is ever missing.
        if image and not getattr(image, "_committed", False):
            return to_browser_safe_image(image)
        return image

    def clean_gallery_images(self):
        files = self.cleaned_data.get("gallery_images") or []
        return [to_browser_safe_image(f) for f in files]


class CarImageInline(admin.TabularInline):
    """Shows already-added gallery images for reorder/delete.
    New images are added via the "Gallery (bulk upload)" field above instead,
    so adding through this inline is disabled."""

    model = CarImage
    extra = 0
    fields = ("image", "sort_order")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display  = ("title", "subtitle", "make", "model", "year", "price", "mileage", "reg", "status")
    list_filter   = ("status", "make", "body_type", "fuel", "transmission", "colour")
    list_editable = ("status",)
    search_fields = ("title", "subtitle", "make", "model", "reg")
    readonly_fields = ("created_at", "updated_at")
    inlines = (CarImageInline,)
    change_form_template = "admin/cars/car/change_form.html"
    form = CarAdminForm

    def get_inline_instances(self, request, obj=None):
        instances = super().get_inline_instances(request, obj)
        if obj is None:
            # Nothing to manage yet on the Add Car page — images come via the bulk field.
            instances = [i for i in instances if not isinstance(i, CarImageInline)]
        return instances

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        files = form.cleaned_data.get("gallery_images") or []
        if files:
            next_order = (
                obj.gallery.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
            ) + 1
            for offset, f in enumerate(files):
                CarImage.objects.create(car=obj, image=f, sort_order=next_order + offset)
            messages.success(request, f"Uploaded {len(files)} gallery image(s).")

        feature_count = 0
        for field_name, category in FEATURE_BULK_FIELDS.items():
            lines = [
                line.strip()
                for line in (form.cleaned_data.get(field_name) or "").splitlines()
                if line.strip()
            ]
            # The box reflects the full current list for its category, so
            # saving syncs to exactly what's in the box (not append-only).
            obj.features.filter(category=category).delete()
            CarFeature.objects.bulk_create([
                CarFeature(car=obj, category=category, text=line) for line in lines
            ])
            feature_count += len(lines)
        messages.success(request, f"Saved {feature_count} feature(s).")

    def response_add(self, request, obj, post_url_continue=None):
        # After creating a new car, land on its edit page (not the changelist)
        # so the gallery (and "Bulk upload images" button) are right there.
        if "_addanother" not in request.POST and "_continue" not in request.POST:
            request.POST = request.POST.copy()
            request.POST["_continue"] = "1"
        return super().response_add(request, obj, post_url_continue)

    def get_urls(self):
        return [
            path(
                "<int:car_id>/bulk-upload-images/",
                self.admin_site.admin_view(self.bulk_upload_images_view),
                name="cars_car_bulk_upload_images",
            ),
            path(
                "<int:car_id>/delete-all-images/",
                self.admin_site.admin_view(self.delete_all_images_view),
                name="cars_car_delete_all_images",
            ),
        ] + super().get_urls()

    def delete_all_images_view(self, request, car_id):
        car = get_object_or_404(Car, pk=car_id)

        if request.method == "POST":
            images = list(car.gallery.all())
            for img in images:
                img.image.delete(save=False)
                img.delete()
            messages.success(request, f"Deleted {len(images)} gallery image(s) from {car.title}.")
            return redirect("admin:cars_car_change", car_id)

        return render(request, "admin/cars/car/delete_all_images.html", {
            "car": car,
            "opts": self.model._meta,
            "title": f"Delete all images — {car.title}",
            "image_count": car.gallery.count(),
        })

    def bulk_upload_images_view(self, request, car_id):
        car = get_object_or_404(Car, pk=car_id)

        if request.method == "POST":
            files = request.FILES.getlist("images")
            if not files:
                messages.error(request, "No files were selected.")
            else:
                next_order = (
                    car.gallery.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
                ) + 1
                created = 0
                skipped = 0
                for offset, f in enumerate(files):
                    is_heic = f.name.lower().endswith((".heic", ".heif"))
                    if not is_heic and (not f.content_type or not f.content_type.startswith("image/")):
                        skipped += 1
                        continue
                    CarImage.objects.create(
                        car=car, image=to_browser_safe_image(f), sort_order=next_order + offset
                    )
                    created += 1
                if created:
                    messages.success(request, f"Uploaded {created} image(s) to {car.title}.")
                if skipped:
                    messages.warning(request, f"Skipped {skipped} non-image file(s).")
            return redirect("admin:cars_car_change", car_id)

        return render(request, "admin/cars/car/bulk_upload_images.html", {
            "car": car,
            "opts": self.model._meta,
            "title": f"Bulk upload images — {car.title}",
        })

    fieldsets = (
        ("Identity", {
            "fields": ("title", "subtitle", "reg", "image", "status")
        }),
        ("Gallery (bulk upload)", {
            "fields": ("gallery_images",),
            "description": "Select 20, 50, 100+ images here — they're added as gallery images on Save.",
        }),
        ("Features (bulk add)", {
            "fields": (
                "exterior_features", "interior_features", "performance_features",
                "size_features", "audio_features",
            ),
            "description": "Paste one feature per line in the matching box — no need to pick a category per line.",
        }),
        ("Classification (filters)", {
            "fields": ("make", "model", "body_type", "fuel", "transmission", "colour")
        }),
        ("Specs", {
            "fields": (
                "year", "engine_cc", "engine", "doors", "seats",
                "mileage", "price", "monthly", "mot_date", "history_check",
                "deposit_amount",
            )
        }),
        ("Detail copy", {
            "fields": ("description", "video_url")
        }),
        ("Location (leave blank for site default)", {
            "fields": ("location_name", "location_address"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Favourite)
class FavouriteAdmin(admin.ModelAdmin):
    list_display   = ("user", "car", "created_at")
    list_filter    = ("created_at",)
    search_fields  = ("user__email", "car__title", "car__make", "car__model")
    list_select_related = ("user", "car")

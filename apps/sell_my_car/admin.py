from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import SellMyCarEnquiry, SellMyCarImage


class EnquiryStatusForm(forms.ModelForm):
    """Reactivating a cancelled enquiry can clash with whoever took its slot.

    The date and time are read-only here, so Django skips the unique
    constraint during validation and the save would otherwise crash.
    """

    def clean_status(self):
        new_status = self.cleaned_data["status"]
        enquiry = self.instance
        if new_status != SellMyCarEnquiry.Status.CANCELLED:
            slot_taken = (
                SellMyCarEnquiry.objects.filter(
                    appointment_date=enquiry.appointment_date,
                    appointment_time=enquiry.appointment_time,
                )
                .exclude(status=SellMyCarEnquiry.Status.CANCELLED)
                .exclude(pk=enquiry.pk)
                .exists()
            )
            if slot_taken:
                raise forms.ValidationError("Another enquiry has since booked this inspection slot.")
        return new_status


class SellMyCarImageInline(admin.TabularInline):
    model = SellMyCarImage
    extra = 0
    can_delete = False
    fields = ["thumbnail"]
    readonly_fields = ["thumbnail"]

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Photo")
    def thumbnail(self, obj):
        url = obj.image.url
        return format_html(
            '<a href="{}" target="_blank" rel="noopener"><img src="{}" alt="Car photo" style="max-height:140px;border-radius:4px;" /></a>',
            url,
            url,
        )


@admin.register(SellMyCarEnquiry)
class SellMyCarEnquiryAdmin(admin.ModelAdmin):
    form = EnquiryStatusForm
    list_display = ["reg", "car", "name", "phone", "inspection_slot", "status", "created_at"]
    list_editable = ["status"]
    list_filter = ["status", "appointment_date", "created_at"]
    search_fields = ["reg", "name", "email", "phone"]
    readonly_fields = [
        "reg", "mileage", "make", "model",
        "name", "email", "phone", "address", "message",
        "appointment_date", "appointment_time", "created_at",
    ]
    inlines = [SellMyCarImageInline]

    def has_add_permission(self, request):
        return False

    def get_changelist_form(self, request, **kwargs):
        kwargs.setdefault("form", EnquiryStatusForm)
        return super().get_changelist_form(request, **kwargs)

    @admin.display(description="Car")
    def car(self, obj):
        return obj.car_label or "—"

    @admin.display(description="Inspection", ordering="appointment_date")
    def inspection_slot(self, obj):
        return f"{obj.appointment_date:%d/%m/%Y} {obj.appointment_time:%H:%M}"

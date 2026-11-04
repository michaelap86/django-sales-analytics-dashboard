from django.contrib import admin

from .models import Category, Customer, Order, OrderItem, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "color"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "sku", "category", "price", "cost"]
    list_filter = ["category"]
    search_fields = ["name", "sku"]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "company", "region", "joined"]
    list_filter = ["region"]
    search_fields = ["name", "email", "company"]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ["product"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "created", "status"]
    list_filter = ["status", "created", "customer__region"]
    search_fields = ["number", "customer__name", "customer__email"]
    date_hierarchy = "created"
    inlines = [OrderItemInline]
    list_select_related = ["customer"]

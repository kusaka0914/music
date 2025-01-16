from django import template

register = template.Library()

@register.filter
def multiply(value, arg):
    return value * arg 

@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={"class": css_class}) 

@register.filter
def split(value, delimiter='\n'):
    """文字列を指定された区切り文字で分割するフィルター"""
    if value:
        return value.split(delimiter)
    return [] 
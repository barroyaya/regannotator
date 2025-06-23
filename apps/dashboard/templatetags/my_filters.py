from django import template

register = template.Library()

@register.filter
def dict_get(dict_obj, key):
    if dict_obj and key:
        return dict_obj.get(str(key)) or dict_obj.get(key)
    return None

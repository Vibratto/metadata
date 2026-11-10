"""Watches API filters."""

from django_filters import BooleanFilter, FilterSet  # type: ignore[import-untyped]

from catalog.filters import NumberInFilter

from .models import Watch


class WatchFilter(FilterSet):  # type: ignore[misc]
    """Filters watches."""

    enabled = BooleanFilter()
    auto_download = BooleanFilter()
    artist = NumberInFilter(field_name="watch_artists__artist_id", distinct=True)

    class Meta:
        """Filterable fields."""

        model = Watch
        fields = ["enabled", "auto_download"]

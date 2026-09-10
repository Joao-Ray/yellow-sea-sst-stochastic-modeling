from datetime import date

import pytest

from src.data.download_oisst import build_url, iter_dates


def test_build_url_points_to_final_daily_file() -> None:
    url = build_url(date(2020, 2, 29))
    assert url.endswith(
        "/202002/oisst-avhrr-v02r01.20200229.nc"
    )
    assert "preliminary" not in url


def test_iter_dates_is_inclusive() -> None:
    days = list(iter_dates(date(1981, 9, 1), date(1981, 9, 3)))
    assert days == [date(1981, 9, 1), date(1981, 9, 2), date(1981, 9, 3)]


def test_iter_dates_rejects_dates_before_record() -> None:
    with pytest.raises(ValueError, match="begins"):
        list(iter_dates(date(1981, 8, 31), date(1981, 9, 1)))

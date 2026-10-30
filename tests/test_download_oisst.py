from datetime import date

import pytest

from src.data.download_oisst import build_url, iter_dates
from src.data.download_oisst import download_file


def test_build_url_points_to_final_daily_file() -> None:
    url = build_url(date(2020, 2, 29))
    assert url.endswith("/202002/oisst-avhrr-v02r01.20200229.nc")
    assert "preliminary" not in url


def test_iter_dates_is_inclusive() -> None:
    days = list(iter_dates(date(1981, 9, 1), date(1981, 9, 3)))
    assert days == [date(1981, 9, 1), date(1981, 9, 2), date(1981, 9, 3)]


def test_iter_dates_rejects_dates_before_record() -> None:
    with pytest.raises(ValueError, match="begins"):
        list(iter_dates(date(1981, 8, 31), date(1981, 9, 1)))


def test_html_response_cannot_be_saved_as_a_successful_download(tmp_path):
    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, **kwargs):
            yield b"<html>server unavailable</html>"

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    destination = tmp_path / "daily.nc"
    with pytest.raises(ValueError, match="not a NetCDF"):
        download_file("https://example.test/daily.nc", destination, Session())
    assert not destination.exists()
    assert not destination.with_suffix(".nc.part").exists()


def test_invalid_cached_file_is_not_silently_skipped(tmp_path):
    path = tmp_path / "daily.nc"
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="overwrite"):
        download_file("https://example.test/daily.nc", path, None)

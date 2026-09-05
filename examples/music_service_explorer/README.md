# Music Service Explorer

A deliberately simple Flask app that demonstrates **every read-only soco
music-service feature** in the cleanest possible way. It runs against the
SoCo checkout in this repository (make sure you are on the `music-services`
branch, which adds `MusicServiceBrowser` and search variants).

**Nothing is ever played or queued.** The app only browses, searches and
inspects metadata.

## Run it

```bash
cd <repo root>
pip install -r examples/music_service_explorer/requirements.txt
python examples/music_service_explorer/app.py
# open http://127.0.0.1:5050
```

A Sonos speaker must be reachable on the network.

## What it demonstrates

| Feature | soco API | Tab |
|---|---|---|
| Speaker / household info | `soco.discovery.any_soco()` | header |
| Configured household accounts | `ConfiguredMusicServiceAccount.get_accounts()` | home |
| Service catalog (106 services) | `MusicService._get_music_services_data()` | sidebar |
| Descriptor (id, auth, capabilities, URIs, desc) | `MusicService.*` attributes | Service info |
| Search categories | `MusicService.available_search_categories` | Service info |
| Search variants (catalog vs library) | `MusicService.available_search_variants` | Service info |
| Search (both APIs) | `MusicService.search()` / `MusicServiceBrowser.search()` | Search |
| Browse containers, recursive, paging | `get_metadata()` on both APIs | Browse |
| Item metadata | `get_media_metadata()` on both APIs | Item metadata |

Every feature panel has a "soco code" snippet showing the equivalent Python.

## Notes

- `MusicServiceBrowser` uses the account credentials Sonos already stores for
  your household, so authenticated services (Apple Music, Amazon, …) work
  without any manual token setup.
- Search defaults to **all variants** for the browser API; pick a single
  variant (e.g. `LibrarySearchTitle`) to scope the search.
- The logo catalog (`get_all_music_services(include_logos=True)`) lives on the
  `music-service-icons` branch; the sidebar shows initials until that API is
  merged here.
- **Favorites remember their account:** a favorite's `cdudn` carries the
  account UID it was saved from (matches the account UDN). If that account
  is gone or broken (provider returns `LoginDisabled`), detect it and let
  the user switch the favorite to another configured account.

import soco

# device = soco.discovery.any_soco()
# print(device.player_name)

# library = soco.music_library.MusicLibrary()
# library.delete_library_share(share_name='//sonoplus.local/sonoplus7')

# Experimenting with strict typing
# def my_function(first: int = 1, second: int = 2) -> int:
#     return first + second
#
#
# result: int = my_function(3, 1)
# print(result)
#
# my_dictionary: dict = {}

library = soco.music_library.MusicLibrary()
shares = library.list_library_shares()

for share in shares:
    print(share)
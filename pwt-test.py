import soco
import time

library = soco.music_library.MusicLibrary()

print()
# print('Before ...')
for share in library.list_library_shares():
    print(share)

# try:
#     r = library.delete_library_share('//sonoplus.local/sonoplus7')
# except soco.exceptions.SoCoUPnPException as error:
#     print(type(error))
#     print('Exception caught: {}'.format(error))
#
# print(type(r))

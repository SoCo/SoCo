import soco
import time
import soco.music_services
import threading

left = soco.SoCo('192.168.0.36')
right = soco.SoCo('192.168.0.37')
study = soco.SoCo('192.168.0.39')

# left.create_stereo_pair(right)
# study.create_stereo_pair(left)
# study.separate_stereo_pair()
# left.separate_stereo_pair()
# left.create_stereo_pair(right)

# -----------------------------------
# k = soco.SoCo('192.168.0.30')
# r = soco.SoCo('192.168.0.32')
# f = soco.SoCo('192.168.0.35')
# b = soco.SoCo('192.168.0.36')
# b2 = soco.SoCo('192.168.0.38')
# s = soco.SoCo('192.168.0.39')

# s.balance = 0, 100
# time.sleep(5)
# s.balance = 100, 0
# time.sleep(5)
# s.balance = 50, 50
# time.sleep(5)
# s.balance = (100, 100)
#
# print(k.player_name, r.player_name, f.player_name,
#       b.player_name, b2.player_name, s.player_name)

# s.group.set_relative_volume('+20')

# f.join(s)
#
# print(s.group.volume)
# print(s.volume)
# s.group.mute = False
# time.sleep(5)
# print(s.group.mute)
# print(s.mute)
# s.group.volume += 10
# time.sleep(3)
# s.group.set_relative_volume(-10)

# time.sleep(1)
# s.set_group_volume(40)

# s.set_relative_group_volume(0)
# f.volume = 60
# f.mute = True
# f.group_mute = True

# a = soco.music_services.Account()
# a.get_accounts()
# print(a)

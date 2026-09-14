import matplotlib
import platform
os = platform.system()
if os == 'Windows':
    font_family = 'YuGothic'
elif os == 'Linux':
    font_family = 'IPAexGothic'
else:  # os == 'Darwin'
    font_family = 'AppleGothic'
font = {'family': font_family, 'size': '15', 'weight': 'bold'}
matplotlib.rc('font', **font)

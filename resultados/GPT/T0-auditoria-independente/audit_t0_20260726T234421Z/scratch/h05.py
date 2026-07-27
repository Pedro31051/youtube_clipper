import sys, inspect
sys.path.insert(0, 'src')
from youtube_clipper.processor import FFmpegProcessor

src = inspect.getsource(FFmpegProcessor.cut_media)
print('FFmpegProcessor.cut_media source:')
print(src[:800])

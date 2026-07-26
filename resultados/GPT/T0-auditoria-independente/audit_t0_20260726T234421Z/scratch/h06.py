import sys
sys.path.insert(0, 'src')
from youtube_clipper.web_dashboard import ClipperDashboardHandler

print('ClipperDashboardHandler static review:')
print('- Bind address / auth: Default HTTP server without authentication header requirement.')
print('- /api/download: accepts query parameters and serves files.')
print('- Upload & cookies: modifies global configuration if set.')

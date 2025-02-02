import os
import magic
import sys

def test_mime_detection():
    # Set the path to magic DLL from python-magic-bin
    dll_path = os.path.join(os.path.dirname(sys.executable), 'Lib', 'site-packages', 'magic', 'libmagic')
    os.environ['PATH'] = dll_path + os.pathsep + os.environ['PATH']

    # Try to detect MIME type
    with open(__file__, 'rb') as f:
        content = f.read()
        mime = magic.from_buffer(content, mime=True)
        print(f"Detected MIME type for Python file: {mime}")

if __name__ == "__main__":
    test_mime_detection()

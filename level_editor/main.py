import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from level_editor.app import App

if __name__ == "__main__":
    App().mainloop()

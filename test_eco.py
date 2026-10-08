import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from utils.cur_processor import get_ecosystems

ecosystems = get_ecosystems(['Amazon Bedrock'])
print(f"Ecosystems returned: {ecosystems}")

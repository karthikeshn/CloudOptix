import glob
import re

for f in glob.glob('*.py'):
    if f in ['refactor_export.py', 'fix_missing.py', 'fix_syntax.py']:
        continue
        
    with open(f, 'r') as file:
        content = file.read()
        
    # We want to replace the broken f-string print block:
    #     print(
    #         f"
    # Excel report created:
    # {filename}"
    #     )
    
    # We can just use regex
    pattern = re.compile(r'print\(\s*f"\nExcel report created:\n\{filename\}"\s*\)', re.MULTILINE)
    content = pattern.sub('print(f"\\\\nExcel report created:\\\\n{filename}")', content)
    
    with open(f, 'w') as file:
        file.write(content)
        
    print(f"Fixed {f}")

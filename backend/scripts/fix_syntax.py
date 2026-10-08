import glob
import os

for f in glob.glob('*.py'):
    if f in ['refactor_export.py', 'fix_missing.py', 'fix_syntax.py']:
        continue
        
    with open(f, 'r') as file:
        content = file.read()
        
    bad_string = 'f"\\nExcel report created:\\n{filename}"'
    good_string = 'f"\\\\nExcel report created:\\\\n{filename}"'
    
    # Actually wait, the literal in the file is literally a newline inside the string!
    # It looks like:
    # f"
    # Excel report created:
    # {filename}"
    
    content = content.replace('f"\\nExcel report created:\\n{filename}"', 'f"\\\\nExcel report created:\\\\n{filename}"')
    
    with open(f, 'w') as file:
        file.write(content)
        
    print(f"Fixed {f}")

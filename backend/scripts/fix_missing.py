new_export_func = """
# ============================================================
# EXPORT TO EXCEL
# ============================================================

def export_to_excel(
    findings,
    filename: str,
):
    from typing import List, Dict, Any
    STANDARD_COLUMNS = [
        "workItemType", "state", "id", "title", "category", "owner",
        "assignedTo", "status", "areaPath", "tags", "commentCount",
        "accountId", "region", "resourceNameOrId", "resourceId",
        "resourceArn", "service", "type", "policy", "effortLevel",
        "message", "recommendation", "description", "currentDailyCost",
        "currentMonthlyCost", "estimatedMonthlySavings", "approvalComments",
        "reasonForRejection", "achievedSavingsMonthly", "month"
    ]

    flat_findings = []
    
    if isinstance(findings, dict):
        findings = [findings]

    for finding in findings:
        flat_finding = {}
        extra_attributes = []
        
        for key, value in finding.items():
            if isinstance(value, (dict, list)):
                import json
                str_val = json.dumps(value, default=str)
            else:
                str_val = value

            if key in STANDARD_COLUMNS:
                flat_finding[key] = str_val
            else:
                extra_attributes.append(f"{key}: {str_val}")
                
        standard_row = {col: "" for col in STANDARD_COLUMNS}
        
        for k, v in flat_finding.items():
            standard_row[k] = v
            
        existing_desc = standard_row.get("description", "")
        if existing_desc is None:
            existing_desc = ""
            
        if extra_attributes:
            extra_str = " | ".join(extra_attributes)
            if existing_desc:
                standard_row["description"] = f"{existing_desc} | {extra_str}"
            else:
                standard_row["description"] = extra_str
                
        flat_findings.append(standard_row)

    import pandas as pd
    df = pd.DataFrame(flat_findings, columns=STANDARD_COLUMNS)
    df.to_excel(filename, index=False)
    print(f"\\nExcel report created:\\n{filename}")
"""

import os
import re

for filename in ["d:\\FinOpsTest\\Snapshot.py", "d:\\FinOpsTest\\EBSunattached.py"]:
    with open(filename, "r") as f:
        content = f.read()

    # insert the function before if __name__ == "__main__":
    if "def export_to_excel" not in content:
        content = content.replace('if __name__ == "__main__":', new_export_func + '\nif __name__ == "__main__":')

    if "EBSunattached.py" in filename:
        content = re.sub(
            r'flat_findings = \[\]\n.*?df\.to_excel\(excel_file, index=False\)\n.*?print\(.*?\)',
            'export_to_excel(findings, "ebs_unattached_report.xlsx")',
            content,
            flags=re.DOTALL
        )

    with open(filename, "w") as f:
        f.write(content)

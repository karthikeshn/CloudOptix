import os
import csv
import glob

CUR_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def get_costs_for_resources(resource_ids: list[str]) -> dict[str, dict]:
    """
    Scans the local CUR files for the given resource IDs.
    Returns a dictionary mapping resource_id -> {"monthly_cost": float, "daily_cost": float}
    """
    if not resource_ids:
        return {}
        
    # Find all CUR csv/csv.gz files in the data directory
    cur_files = glob.glob(os.path.join(CUR_DATA_DIR, "*.csv"))
    
    if not cur_files:
        return {}
        
    # We will aggregate costs across all found CUR chunks (in case they are split)
    cost_map = {rid: 0.0 for rid in resource_ids}
    
    for file_path in cur_files:
        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                headers = next(reader)
                
                try:
                    res_idx = headers.index('lineItem/ResourceId')
                    cost_idx = headers.index('lineItem/UnblendedCost')
                except ValueError:
                    # Skip files that aren't CUR reports
                    continue
                    
                for row in reader:
                    if len(row) <= max(res_idx, cost_idx):
                        continue
                        
                    cur_res_id = row[res_idx]
                    
                    for r_id in resource_ids:
                        if r_id != "unknown" and r_id in cur_res_id:
                            try:
                                cost_map[r_id] += float(row[cost_idx])
                            except ValueError:
                                pass
        except Exception as e:
            print(f"Error reading CUR file {file_path}: {e}")
            
    # Format the output
    result = {}
    for r_id, total_cost in cost_map.items():
        if total_cost > 0:
            result[r_id] = {
                "monthly_cost": total_cost,
                "daily_cost": total_cost / 30.0
            }
            
    return result

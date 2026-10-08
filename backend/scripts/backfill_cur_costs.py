import sqlite3
import csv
import json
import sys

def main():
    db_path = 'd:/FinOpsDashboard/backend/data/finops_v4.db'
    csv_path = 'd:/FinOpsDashboard/backend/data/FinOpstestkarthik-00001.csv'

    print("Loading CUR data...")
    cur_costs = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            res_idx = headers.index('lineItem/ResourceId')
            cost_idx = headers.index('lineItem/UnblendedCost')
            
            for row in reader:
                if len(row) <= max(res_idx, cost_idx):
                    continue
                r_id = row[res_idx]
                try:
                    cost = float(row[cost_idx])
                except ValueError:
                    cost = 0.0
                
                if r_id not in cur_costs:
                    cur_costs[r_id] = 0.0
                cur_costs[r_id] += cost
    except Exception as e:
        print(f"Error reading CUR: {e}")
        sys.exit(1)
        
    print("Connecting to database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, resource_id, details FROM tickets WHERE resource_id IS NOT NULL")
    tickets = cursor.fetchall()
    
    updates = 0
    
    for ticket_id, t_res_id, details_str in tickets:
        if not t_res_id or t_res_id == 'unknown':
            continue
            
        # Find the total cost for this resource in the CUR
        monthly_cost = 0.0
        found = False
        for cur_id, cost in cur_costs.items():
            if t_res_id in cur_id:
                monthly_cost += cost
                found = True
                
        if found:
            daily_cost = monthly_cost / 30.0
            
            # Format as currency
            m_cost_str = f"${monthly_cost:.2f}"
            d_cost_str = f"${daily_cost:.2f}"
            
            # Update the JSON details
            try:
                details = json.loads(details_str or '{}')
            except:
                details = {}
                
            # Replace placeholder keys with actual data
            # Check for different case variations just in case
            for key in list(details.keys()):
                if key.upper() == 'CURRENTMONTHLYCOST' or key.upper() == 'MONTHLY_COST':
                    del details[key]
                if key.upper() == 'CURRENTDAILYCOST' or key.upper() == 'DAILY_COST':
                    del details[key]
                    
            details['CURRENTMONTHLYCOST'] = m_cost_str
            details['CURRENTDAILYCOST'] = d_cost_str
            
            # Update the database
            new_details_str = json.dumps(details)
            
            cursor.execute("""
                UPDATE tickets 
                SET details = ?, potential_savings = ? 
                WHERE id = ?
            """, (new_details_str, m_cost_str, ticket_id))
            
            updates += 1
            print(f"Updated Ticket #{ticket_id} ({t_res_id}): Monthly {m_cost_str}, Daily {d_cost_str}")
            
    conn.commit()
    conn.close()
    print(f"\nSuccessfully updated {updates} tickets with actual CUR costs.")

if __name__ == '__main__':
    main()

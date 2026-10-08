# FinOps Ticket Lifecycle Workflow

### Phase 1: Discovery & Ticket Creation
1. **Log In & Run:** You (or an engineer) log into the FinOps Dashboard, go to the scripts page, select one or multiple scripts, and click "Run".
2. **Scan AWS:** The scripts connect to AWS and scan for cost-saving opportunities based on their logic (e.g., finding an unattached EBS volume).
3. **Generate Ticket:** When the script finds a resource that should be cleaned up, it **does not** delete it. Instead, it automatically creates a new Ticket in the database. 
4. **Initial State:** The ticket is saved with the details (Resource ID, Savings, AWS Account) and is set to a **`Pending`** status.

### Phase 2: Manager Review & Approval
5. **The Manager Dashboard:** An Engineering Manager logs into the Dashboard and navigates to a new "Approvals" menu.
6. **Review:** They see a table listing all the `Pending` tickets.
7. **Make a Decision:** The manager selects a ticket and chooses to either **Approve** or **Reject** it. 
   * *If Rejected:* They must type a justification, and the ticket is closed as `Rejected`.
   * *If Approved:* The ticket status changes to **`Approved`**. Absolutely no automated deletion happens.

### Phase 3: The Assignment
8. **The Assignment Menu:** Once a ticket is `Approved`, it moves out of the Pending list and drops into a completely separate menu (e.g., "Approved Tasks").
9. **Assigning the Work:** The manager goes to this "Approved Tasks" menu, selects the approved ticket, and **Assigns** it to a specific engineer (e.g., "John Doe").
10. **Notification:** The system sends an email to John Doe saying: *"You have been assigned an approved FinOps task to delete volume vol-123."*

### Phase 4: Manual Action & Completion
11. **The Engineer Acts:** John Doe logs into the Dashboard, sees his assigned task, and then goes to the AWS Console (or runs a specific script) to **manually** delete the volume.
12. **Mark as Done:** Once John Doe finishes the job, he comes back to the FinOps Dashboard and clicks a button to mark the ticket as **`Completed`**.

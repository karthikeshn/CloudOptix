# 🚨 THE HYBRID TESTING MANDATE 🚨
*(This is the central architectural mandate for testing and deploying FinOps scripts in this repository. It must NEVER be forgotten.)*

## 1. The Core Philosophy
Write the code EXACTLY ONCE for production. 
Do not write test-specific code inside the FinOps scripts. We test safely by manipulating the environment (Smoke and Mirrors), not the code.

## 2. The Hybrid Execution Flow
When a script runs in the testing environment (`br-moto` branch), the following flow MUST occur:

1. **Fake Infrastructure (Moto):** EC2/EBS infrastructure is 100% fake. Moto intercepts standard `boto3` calls and builds resources purely in RAM.
2. **Original Fetching Code:** The Python script uses standard, production-ready `boto3` code to find these resources based on strict FinOps rules.
3. **Capture Pricing Parameters:** During the scan, the script MUST capture the exact metadata parameters required by the Pricing API (e.g., `databaseEngine`, `volumeApiName`, `instanceType`).
4. **Fake CUR Cost (Database):** The script queries the historical cost from a fake database (`test_finops.db`) that contains a mock CUR row with the exact schema as the real AWS CUR file, matching the Moto-generated fake Resource ID.
5. **Real Pricing API (The Hybrid Breakout):** The script uses the `region_mapping.py` logic, breaks OUT of the Moto sandbox, uses REAL AWS credentials, and hits the REAL AWS internet Pricing API to find the exact future market cost.
6. **Real Recommendations:** The FinOps recommendations and the final calculated savings are 100% authentic and accurate.

If the script successfully completes this flow locally, it is guaranteed to work in production with real credentials.

## 3. The 7-Step Pre-Flight Testing Checklist
Every single time a new FinOps resource optimization script is created and tested, this checklist MUST be completed in order:

### The 5 Architecture Pillars
1. **Moto Fake Resources:** Write the test setup to spawn 1 or more fake resources (e.g., EC2, EBS) so the scanner has something to find.
2. **Fake CUR Data:** Inject a fake historical cost row into the `test_finops.db` matching the newly generated Moto fake Resource ID.
3. **Logic Script:** Run the production Python code that uses `boto3` to scan for FinOps violations.
4. **Pricing Script:** Run the production Pricing Module to pull the historical CUR cost and calculate the future API cost.
5. **Region Mapper:** Ensure the Pricing API translation uses the `region_mapping.py` module perfectly.

### The 2 Setup Enablers
6. **Environment Overrides:** Set `AWS_ACCESS_KEY_ID="testing"` and `AWS_SECRET_ACCESS_KEY="testing"` to prevent early boto3 crashes, and set `DATABASE_URL` to point exclusively to the test database.
7. **Boto3 Isolation (The Moto Escape Hatch):** Explicitly engineer the test so that Moto's shield covers the EC2/S3/RDS scans, but is disabled or bypassed when calling the real AWS Pricing API over the internet.

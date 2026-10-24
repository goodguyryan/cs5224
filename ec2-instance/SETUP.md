# Deploy Parliament in Five on EC2

Follow these steps in order to run the real application with DynamoDB and S3.
The target is **Ubuntu Server 24.04 LTS, x86_64**, in **Singapore
(`ap-southeast-1`)**. Commands marked **EC2 terminal** are Linux commands run
after connecting to the instance; commands marked **your computer** run locally.

The deployed request path is:

```text
Browser -> EC2 public address:3000 -> Express
                                     |-- built React frontend
                                     |-- POST /api/summary -> DynamoDB
                                     `-- POST /api/detail -> DynamoDB -> private S3
```

Express serves both the frontend files and APIs. No Nginx installation or
reverse proxy is part of this setup. Port 5173 is used only by local Vite
development and is not needed on EC2. This guide deploys the application's
current HTTP server; it does not configure HTTPS or certificates.

## 1. Record the values you will use

Collect these before creating resources. Replace all `YOUR_...` placeholders in
commands and configuration with your own values before using them.

| Value                         | Example or required format                                                     | Used in                                                             |
| ----------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| AWS account ID                | Your 12-digit account ID                                                       | IAM policy resource ARNs                                            |
| AWS Region                    | `ap-southeast-1`                                                               | EC2, DynamoDB, S3, backend configuration                            |
| DynamoDB table name           | `parliament-in-five-reports`                                                   | Table creation, IAM policy, backend `.env`                          |
| Summary bucket name           | A unique lowercase name such as `parliament-in-five-summaries-YOUR_ACCOUNT_ID` | S3 creation, IAM policy, backend `.env`, each item's `S3BucketLink` |
| Repository clone URL          | `https://github.com/YOUR_OWNER/YOUR_REPO.git`                                  | `git clone`                                                         |
| Branch or commit              | The branch/commit containing this application                                  | Deployment checkout                                                 |
| SSH key file on your computer | `C:\Users\YOUR_USER\Downloads\parliament-key.pem`                              | SSH connection                                                      |
| EC2 public IPv4 address       | Copy from the running instance                                                 | SSH and browser access                                              |
| HTTP port                     | `3000` in this guide                                                           | Backend `.env`, security group, browser URL                         |
| First report summary ID       | For example `report-001`                                                       | DynamoDB item, detail verification                                  |
| First official report URL     | The actual complete URL of that report on the Parliament website               | DynamoDB `ActualReportLink`                                         |
| First summary object key      | For example `summaries/report-001.json`                                        | S3 object and DynamoDB `S3BucketLink`                               |

Use the same Region for EC2, the table, and the summary bucket. For the first
deployment, keep these resources in the same AWS account. If you already have
the table and bucket, reuse them after checking the schema and permissions below.

## 2. Make the application available to EC2

**Your computer, repository root:** make sure the application and its lockfiles
are committed and pushed to a repository the instance can access. Review
`git status` before committing. For a deployment commit containing this work:

```sh
git add .gitignore package.json package-lock.json ec2-instance
git status
git commit -m "Add Express and React Hansard reader"
git push
```

Skip the commit if these files are already committed. If your branch has no
upstream, use the push command appropriate to your remote and branch. Do not
commit `.env`, `node_modules`, or build output; these paths are ignored.
EC2 configuration files will be created on the instance.

## 3. Create or check the DynamoDB table

**AWS Console:** open [DynamoDB](https://console.aws.amazon.com/dynamodb/) and
select **Singapore (`ap-southeast-1`)**.

1. Open **Tables -> Create table**.
2. Set **Table name** to your chosen name, for example `parliament-in-five-reports`.
3. Set **Partition key** to exactly `HansardReportSummaryId`, type **String**.
4. Leave the **Sort key** unset. The application performs a direct lookup using
   only the partition key; a secondary index on this attribute is insufficient.
5. Use **On-demand** capacity for this prototype, then create the table.
6. Wait until its status is **Active** and record its table ARN for the IAM policy.

Only the key is defined when creating the table. Other attributes are added to
each item. Attribute names are case-sensitive. Keep this table dedicated to
approved public reports; the application lists every item and has no draft-status
filter. See AWS's [table creation instructions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/getting-started-step-1.html).

## 4. Create or check the private S3 summary bucket

**AWS Console:** open [S3](https://console.aws.amazon.com/s3/).

1. Choose **Create bucket**, select a **General purpose** bucket, and use the
   unique bucket name from step 1.
2. Select **Singapore (`ap-southeast-1`)**.
3. Keep **Object Ownership: Bucket owner enforced** and **Block all public access** enabled.
4. For a straightforward first deployment, select **server-side encryption with
   Amazon S3 managed keys (SSE-S3)**. If your existing bucket uses a customer-managed
   KMS key, add the decrypt permission described in step 6.
5. Create the bucket. Do not enable S3 static website hosting; Express serves the website.

The backend authenticates its S3 reads; readers never need public object access.
See AWS's [bucket creation guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/create-bucket-overview.html).

## 5. Upload the first summary and add its metadata

### 5.1 Upload the summary JSON

**Your computer:** create a UTF-8 file named `report-001.json` with these two fields:

```json
{
  "title": "YOUR_ACTUAL_SUMMARY_TITLE",
  "body": "Your summary's first paragraph.\n\nYour summary's second paragraph."
}
```

Replace the sample content with your approved summary. Both values must be
nonempty strings. Use `\n\n` inside JSON strings for paragraph breaks. The body
is plain text; HTML and Markdown are not interpreted. Do not add dates, an ID,
or any other fields to this object. The default maximum object size is 1 MiB.

**S3 Console:** open your bucket, create a `summaries` folder, and upload the file
inside it. The resulting object key must be `summaries/report-001.json`.
If choosing object metadata during upload, set `Content-Type` to `application/json`.
Leave the object private.

Record its S3 URI:

```text
s3://YOUR_SUMMARY_BUCKET/summaries/report-001.json
```

Use this stable URI in DynamoDB. The backend also supports standard regional
HTTPS S3 object URLs, but no expiring signed URL is required. An official
Hansard URL, a folder URL, or an arbitrary file-sharing URL cannot be used here.

### 5.2 Create the DynamoDB item

**DynamoDB Console:** open your table, choose **Explore table items -> Create
item**, and use the form editor to add the following attributes, all as **String**:

| Attribute                | Value to enter                                          |
| ------------------------ | ------------------------------------------------------- |
| `HansardReportSummaryId` | `report-001`                                            |
| `DateOfRelease`          | The actual release date, formatted `YYYY-MM-DD`         |
| `ActualReportLink`       | The full official report URL, beginning with `https://` |
| `S3BucketLink`           | `s3://YOUR_SUMMARY_BUCKET/summaries/report-001.json`    |

For reference, the application sees an item shaped like this:

```json
{
  "HansardReportSummaryId": "report-001",
  "DateOfRelease": "2026-10-20",
  "ActualReportLink": "https://YOUR_ACTUAL_OFFICIAL_REPORT_URL",
  "S3BucketLink": "s3://YOUR_SUMMARY_BUCKET/summaries/report-001.json"
}
```

The date above is an example; replace it with the real release date, not the
sitting date. This example is ordinary application JSON; use the String fields
in the console form instead of pasting it into an editor expecting DynamoDB's
typed `{"S":"..."}` JSON format.

Save the item. Confirm that the bucket name and object key match the uploaded
file exactly. Upload each summary successfully before adding its archive item.

## 6. Create the EC2 application's IAM role

**AWS Console:** open [IAM](https://console.aws.amazon.com/iam/).

1. Go to **Policies -> Create policy -> JSON**.
2. Paste the following, replacing account ID, table name, and bucket name:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadReportMetadata",
      "Effect": "Allow",
      "Action": ["dynamodb:Scan", "dynamodb:GetItem"],
      "Resource": "arn:aws:dynamodb:ap-southeast-1:YOUR_ACCOUNT_ID:table/YOUR_DYNAMODB_TABLE"
    },
    {
      "Sid": "ReadSummaryObjects",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::YOUR_SUMMARY_BUCKET/*"
    }
  ]
}
```

3. Save it as `ParliamentInFiveReadPolicy`.
4. Go to **Roles -> Create role**. Select **AWS service**, then **EC2** as the
   use case. Attach `ParliamentInFiveReadPolicy`.
5. Name the role `ParliamentInFiveEC2Role` and create it.

If using customer-managed KMS encryption, add this statement to the policy's
`Statement` array and allow this role in that key's key policy:

```json
{
  "Sid": "DecryptSummaryObjects",
  "Effect": "Allow",
  "Action": "kms:Decrypt",
  "Resource": "arn:aws:kms:ap-southeast-1:YOUR_ACCOUNT_ID:key/YOUR_KEY_ID"
}
```

The application receives temporary credentials through the attached role.
Do not put `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or session tokens in
the frontend or backend configuration for this EC2 setup. The operator uploading
content needs their own write permissions; the reader role is read-only.
See [IAM roles for EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html).

## 7. Launch and configure EC2

**AWS Console:** open [EC2](https://console.aws.amazon.com/ec2/) in Singapore
and choose **Launch instance**.

1. Name it `parliament-in-five`.
2. Choose **Ubuntu Server 24.04 LTS**, **64-bit (x86)**. The Node installation
   commands below use x86_64 binaries; ARM instances require the ARM64 download.
3. Choose an instance with enough memory for dependency installation and builds.
   A very small instance may need more memory if TypeScript or Vite is killed
   during a build; the exact instance size is your deployment choice.
4. Create or select a key pair. Download and keep the `.pem` file on your computer.
5. Choose a public subnet with a route to an Internet Gateway and enable
   **Auto-assign public IP** for this direct-access setup.
6. Configure inbound security-group rules:

| Type       | Port     | Source                                                                                                  |
| ---------- | -------- | ------------------------------------------------------------------------------------------------------- |
| SSH        | TCP 22   | Your administrator IP, using **My IP**                                                                  |
| Custom TCP | TCP 3000 | Your IP during verification; `0.0.0.0/0` when the public site should be accessible to all IPv4 visitors |

7. Keep outbound access available for package downloads and AWS HTTPS requests.
   If your organisation restricts egress, arrange HTTPS access to the package
   registries, S3, and DynamoDB, or appropriate VPC endpoints.
8. Under **Advanced details -> IAM instance profile**, select `ParliamentInFiveEC2Role`.
   Require **IMDSv2** in the metadata settings and leave metadata access enabled.
9. Launch the instance, wait for status checks, and record its public IPv4 address.

For an existing instance, attach the role through **Actions -> Security -> Modify
IAM role**. The AWS [EC2 launch guide](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html)
explains the instance, key-pair, and network settings.

Port 3000 is the browser-facing port in this guide. There is no need to open
5173 or make S3 public. If you change the application port later, update the
security group and the URL you use to access it.

## 8. Connect and install Node.js 24

### 8.1 Connect from your computer

**Your computer, PowerShell:** replace the key path and IP:

```powershell
ssh -i "C:\Users\YOUR_USER\Downloads\parliament-key.pem" ubuntu@YOUR_EC2_PUBLIC_IP
```

For macOS/Linux, restrict key permissions first with `chmod 400 /path/to/key.pem`,
then use `ssh -i /path/to/key.pem ubuntu@YOUR_EC2_PUBLIC_IP`.
The following commands run inside that SSH session.

### 8.2 Install system tools

**EC2 terminal:**

```sh
sudo apt-get update
sudo apt-get install -y ca-certificates curl xz-utils git nano
uname -m
```

Expected architecture: `x86_64`. Stop and use an ARM64 Node build if it says `aarch64`.

### 8.3 Install the official Node.js binary

Skip this installation if `node --version` already reports `v24.x.x` and npm is
available. Otherwise, the following uses the official Node.js **24.22.1** release.
You may replace the version with a newer **24.x** release from the
[official Node download page](https://nodejs.org/en/download). The project's
package manifests require Node 24.

```sh
NODE_VERSION=24.22.1
NODE_DOWNLOAD_DIR="$(mktemp -d /tmp/parliament-node.XXXXXX)"
cd "$NODE_DOWNLOAD_DIR"

curl -fSLO "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz"
curl -fSLO "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt"
sha256sum --check --ignore-missing SHASUMS256.txt
```

Verify the archive reports **OK**. Stop if downloading or checksum verification
fails. Then install it in a stable location accessible to the background service:

```sh
sudo mkdir -p /opt/node24
sudo tar -xJf "node-v${NODE_VERSION}-linux-x64.tar.xz" --strip-components=1 -C /opt/node24
sudo ln -sfn /opt/node24/bin/node /usr/local/bin/node
sudo ln -sfn /opt/node24/bin/npm /usr/local/bin/npm
sudo ln -sfn /opt/node24/bin/npx /usr/local/bin/npx
hash -r

node --version
npm --version
command -v node
```

Expected: Node `v24.x.x`, an npm version, and a valid executable path. If using
an existing installation, record its absolute Node path for step 13. Avoid an
installation confined to an interactive shell if a system service cannot access it.

## 9. Download the repository and create the service user

**EC2 terminal, logged in as `ubuntu`:**

```sh
sudo useradd --system --no-create-home --shell /usr/sbin/nologin parliament
sudo mkdir -p /opt/parliament-in-five
sudo chown ubuntu:ubuntu /opt/parliament-in-five
git clone YOUR_REPOSITORY_URL /opt/parliament-in-five
cd /opt/parliament-in-five
git status
git log -1 --oneline
```

Run `useradd` only on the first setup; if `id parliament` already succeeds,
reuse that user. The `parliament` account will run Express, while `ubuntu`
manages checkout/builds. The clone URL must be your repository's real URL.
For a private repository, configure read access for the `ubuntu` account using
your Git provider's supported authentication, such as a read-only deploy key.
Do not embed a token in the clone URL or commit it in configuration.

If deploying a branch other than the default, run `git switch YOUR_BRANCH` now.
Confirm the checkout contains `ec2-instance/frontend` and `ec2-instance/backend`.
If the application was already cloned here, use the existing checkout and fetch
the desired revision instead of cloning into a nonempty directory.

## 10. Configure the frontend and backend environment files

### 10.1 Frontend configuration

**EC2 terminal, repository root:**

```sh
cp ec2-instance/frontend/.env.example ec2-instance/frontend/.env
nano ec2-instance/frontend/.env
```

On first setup, use:

```dotenv
VITE_API_BASE_URL=/api
VITE_API_TIMEOUT_MS=30000
DEV_PORT=5173
DEV_API_PROXY_TARGET=http://127.0.0.1:3000
```

| Variable               | What you should do                                                                                                                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL`    | Keep `/api`. A browser visiting `http://YOUR_EC2_PUBLIC_IP:3000` will call `http://YOUR_EC2_PUBLIC_IP:3000/api/summary` and `/api/detail`. No EC2 IP, S3 URL, or DynamoDB URL needs to be entered here. |
| `VITE_API_TIMEOUT_MS`  | Keep `30000` initially. It is the frontend timeout in milliseconds; supported positive integer range is up to `120000`.                                                                                 |
| `DEV_PORT`             | Leave `5173`. This setting applies only when running Vite for development.                                                                                                                              |
| `DEV_API_PROXY_TARGET` | Leave as shown. This is only the local Vite development proxy; it is not a production server or EC2 dependency.                                                                                         |

Vite embeds public `VITE_*` values when building. Editing them requires another
frontend build. They must never contain secrets. If you already use additional
Vite environment files, such as `.env.production` or `.env.local`, check those
too so they do not override the intended API base.

### 10.2 Backend configuration

```sh
cp ec2-instance/backend/.env.example ec2-instance/backend/.env
nano ec2-instance/backend/.env
```

Set the complete file to the following, replacing the table and bucket placeholders:

```dotenv
NODE_ENV=production
HOST=0.0.0.0
PORT=3000
AWS_REGION=ap-southeast-1
DYNAMODB_TABLE_NAME=YOUR_DYNAMODB_TABLE
S3_SUMMARY_BUCKET=YOUR_SUMMARY_BUCKET
FRONTEND_DIST_PATH=../frontend/dist
AWS_CONNECTION_TIMEOUT_MS=3000
AWS_REQUEST_TIMEOUT_MS=10000
AWS_MAX_ATTEMPTS=2
MAX_SUMMARY_BYTES=1048576
LOG_LEVEL=info
```

| Variable                    | Required action / meaning                                                                                                                                |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NODE_ENV`                  | Set `production`. Startup requires the built frontend to exist.                                                                                          |
| `HOST`                      | Set `0.0.0.0` so Express accepts connections through the instance's network interface. `127.0.0.1` would accept only connections originating inside EC2. |
| `PORT`                      | Use `3000`, matching the inbound security-group rule and browser URL.                                                                                    |
| `AWS_REGION`                | Match the actual table and bucket Region. This guide uses `ap-southeast-1`.                                                                              |
| `DYNAMODB_TABLE_NAME`       | Enter only the exact table name, not its ARN, console link, or service URL.                                                                              |
| `S3_SUMMARY_BUCKET`         | Enter only the exact bucket name, not `s3://`, an object key, ARN, or HTTPS URL.                                                                         |
| `FRONTEND_DIST_PATH`        | Keep `../frontend/dist`. It resolves relative to the backend folder.                                                                                     |
| `AWS_CONNECTION_TIMEOUT_MS` | Keep `3000` initially; connection timeout per AWS request.                                                                                               |
| `AWS_REQUEST_TIMEOUT_MS`    | Keep `10000` initially; AWS request timeout per attempt.                                                                                                 |
| `AWS_MAX_ATTEMPTS`          | Keep `2` initially; supported range is 1–5 attempts.                                                                                                     |
| `MAX_SUMMARY_BYTES`         | Keep `1048576` (1 MiB) unless approved summaries need a larger limit. Supported maximum is 10 MiB.                                                       |
| `LOG_LEVEL`                 | Use `info` for startup and error logs. Other supported values are `error` and `silent`.                                                                  |

The SDK determines DynamoDB/S3 service URLs from `AWS_REGION`; no database URL
needs to be added. Individual S3 object URIs belong in DynamoDB's `S3BucketLink`.
The EC2 public IP belongs in your browser/SSH command, not in either environment file.

Protect the backend configuration while allowing the service account to read it:

```sh
sudo chgrp parliament ec2-instance/backend/.env
chmod 640 ec2-instance/backend/.env
```

Copy the example files only during initial setup. For later deployments, edit
your existing `.env` files so you do not overwrite real resource names. Process
environment variables take precedence over backend `.env` values.

## 11. Install dependencies, check, and build

**EC2 terminal:**

```sh
cd /opt/parliament-in-five
npm --prefix ec2-instance/frontend ci --include=dev
npm --prefix ec2-instance/backend ci --include=dev
npm --prefix ec2-instance/frontend run check
npm --prefix ec2-instance/backend run check
npm --prefix ec2-instance/frontend run build
npm --prefix ec2-instance/backend run build
ls ec2-instance/frontend/dist/index.html
ls ec2-instance/backend/dist/server.js
```

Stop and fix an error before continuing. Development dependencies are included
because TypeScript, ESLint, and Vite are needed during this build. The runtime
entry point is `ec2-instance/backend/dist/server.js`. Frontend output stays on
EC2's filesystem; S3 stores only summary JSON objects in this setup.

## 12. Start the real server and verify both APIs

### 12.1 First start in the foreground

**EC2 terminal, repository root:**

```sh
npm --prefix ec2-instance/backend start
```

Wait for the listening message and confirm there is no following startup error.
Use this production command for real AWS data. `npm run start:local` selects
fictional in-memory data and always binds to loopback; it is only for local previews.

### 12.2 Verify from a second SSH terminal

Leave the first terminal running and open another SSH connection to the same EC2:

```sh
curl -i http://127.0.0.1:3000/api/health
curl -i -X POST http://127.0.0.1:3000/api/summary
curl -i -X POST http://127.0.0.1:3000/api/detail \
  -H 'Content-Type: application/json' \
  -d '{"hansardSummaryId":"report-001"}'
curl -sS -D - -o /dev/null http://127.0.0.1:3000/
curl -sS -D - -o /dev/null http://127.0.0.1:3000/summary/report-001
```

Use the actual summary ID if different. Expect:

- Health: HTTP 200 and `{"status":"ok"}`. This checks the process, not AWS access.
- Summary: HTTP 200 with an array containing `DateOfRelease`, `ActualReportLink`,
  and `HansardReportSummaryId`. An empty table returns `[]`.
- Detail: HTTP 200 with only `title` and `body`, verifying DynamoDB and S3 access.
- Homepage and reader URL: HTTP 200 with HTML headers. A direct reader refresh
  returns React, after which the browser requests its detail data.

A valid request for an unknown ID returns 404. Invalid request bodies return 400. Internal AWS or stored-content failures return 500; inspect the server
terminal for the operational error.

### 12.3 Verify from your computer's browser

Open this exact URL with **http** and the port included:

```text
http://YOUR_EC2_PUBLIC_IP:3000
```

Check that your real release date appears, the official-report button opens the
correct report, the summary renders, Back home works, and refreshing a summary
URL works. With more than 20 records, verify pagination. The backend loads all
metadata and React displays 20 rows per page.

If these checks pass, press **Ctrl+C in the first SSH terminal** before step 13
so only one process owns port 3000.

## 13. Keep Express running after SSH disconnects

Use Ubuntu's built-in **systemd** to supervise Node and start it after a reboot.
Browser traffic still goes directly to Express. These instructions create a
service on EC2 only, with no `deploy` folder in the repository. See the
[systemd service documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html).

**EC2 terminal:**

```sh
sudo nano /etc/systemd/system/parliament-in-five.service
```

Paste and save:

```ini
[Unit]
Description=Parliament in Five Express server
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=parliament
Group=parliament
WorkingDirectory=/opt/parliament-in-five/ec2-instance/backend
EnvironmentFile=/opt/parliament-in-five/ec2-instance/backend/.env
ExecStart=/opt/node24/bin/node /opt/parliament-in-five/ec2-instance/backend/dist/server.js
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
KillSignal=SIGTERM
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
UMask=0027

[Install]
WantedBy=multi-user.target
```

If you installed Node elsewhere, replace `/opt/node24/bin/node` with its actual
absolute executable path. If you changed the checkout location, update all three
application paths in this unit. The service account needs read access to the
application and `.env`; it needs no write access to the checkout. Keep the
application and Node outside `/home` when using `ProtectHome=true`.

Check file access, validate the unit, and start it:

```sh
sudo -u parliament test -r /opt/parliament-in-five/ec2-instance/backend/.env
sudo -u parliament test -r /opt/parliament-in-five/ec2-instance/frontend/dist/index.html
sudo -u parliament test -x /opt/node24/bin/node
sudo systemd-analyze verify /etc/systemd/system/parliament-in-five.service
sudo systemctl daemon-reload
sudo systemctl enable --now parliament-in-five
sudo systemctl status parliament-in-five --no-pager
```

Use your actual Node path in `test -x` too. Expected status: **active (running)**.
Re-run step 12's HTTP checks. You can now disconnect SSH; the service continues.

Useful commands:

```sh
sudo journalctl -u parliament-in-five -n 100 --no-pager
sudo journalctl -u parliament-in-five -f
sudo systemctl restart parliament-in-five
sudo systemctl stop parliament-in-five
sudo systemctl start parliament-in-five
```

Ctrl+C while following `journalctl -f` exits log viewing; it does not stop Express.
Do not run foreground `npm start` while this service already owns port 3000.

## 14. Know which links and settings change later

| Change                                  | Where to change it                                                    | What to do afterwards                                        |
| --------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------ |
| Publish another report                  | Upload its title/body JSON to S3, then add its DynamoDB metadata item | Refresh the archive; no rebuild/restart is required          |
| Correct a report link or release date   | DynamoDB `ActualReportLink` / `DateOfRelease`                         | Refresh the archive                                          |
| Move a summary object                   | Upload it, then update that item's `S3BucketLink`                     | Reload the summary                                           |
| Change table, bucket, or Region         | Backend `.env` and matching IAM resource ARNs                         | Restart Express; configure the real data resources as needed |
| Change HTTP port                        | Backend `PORT`, EC2 security-group rule, browser URL                  | Restart Express                                              |
| Change frontend API base/timeout        | Frontend `.env`                                                       | Rebuild React, then refresh the browser                      |
| Change backend timeout/logging settings | Backend `.env`                                                        | Restart Express                                              |
| EC2 public IP changes after stop/start  | Browser/SSH URLs and any DNS record                                   | `/api` stays valid without rebuilding React                  |

For a stable address, associate an Elastic IP or manage a DNS record pointing at
the instance. A domain pointing directly here uses `http://YOUR_DOMAIN:3000`.
DNS alone does not configure HTTPS; the current server does not load certificates
or listen for HTTPS connections.

## 15. Deploy a later code update

This simple procedure has a short service interruption. Preserve existing `.env`
files and record the previous commit in case you need to return to it.

**EC2 terminal:**

```sh
cd /opt/parliament-in-five
git status
git rev-parse HEAD
sudo systemctl stop parliament-in-five
git pull --ff-only
npm --prefix ec2-instance/frontend ci --include=dev
npm --prefix ec2-instance/backend ci --include=dev
npm --prefix ec2-instance/frontend run check
npm --prefix ec2-instance/backend run check
npm --prefix ec2-instance/frontend run build
npm --prefix ec2-instance/backend run build
sudo systemctl start parliament-in-five
sudo systemctl status parliament-in-five --no-pager
```

Resolve local Git changes before pulling. Stop if any install/check/build fails;
fix it before starting the service. Do not recopy `.env.example` over live
configuration. Re-run both API checks and open the homepage after the update.

## 16. Troubleshooting

| Symptom                                        | Checks and action                                                                                                                                                                       |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `EADDRINUSE` on port 3000                      | Run `sudo ss -ltnp 'sport = :3000'` and identify the owner. Stop the old foreground process with Ctrl+C in its terminal, or stop the existing service before starting another instance. |
| Browser cannot reach EC2, but local curl works | Check `HOST=0.0.0.0`, inbound TCP 3000, the current public IP, and the subnet's public route. If UFW is enabled, allow the chosen port there too.                                       |
| Invalid configuration / placeholder error      | Replace resource-name placeholders. Use bucket/table names only. Check conflicting process environment variables.                                                                       |
| Frontend build is missing                      | Build the frontend and check `FRONTEND_DIST_PATH=../frontend/dist`.                                                                                                                     |
| `CredentialsProviderError`                     | Check the attached EC2 role and enabled metadata access. Remove stale manual credential/profile settings from the service configuration.                                                |
| `AccessDenied` / `AccessDeniedException`       | Check account ID, Region, table ARN, bucket ARN, and any denying bucket/KMS/organisation policy.                                                                                        |
| DynamoDB `ResourceNotFoundException`           | Check `DYNAMODB_TABLE_NAME`, `AWS_REGION`, and the role's account.                                                                                                                      |
| DynamoDB key-schema validation error           | Require String partition key `HansardReportSummaryId` with no sort key.                                                                                                                 |
| Summary list returns 500                       | Check logs, scan permission, and every item's three metadata fields. An invalid stored date/URL/ID can fail the complete list request.                                                  |
| List works but detail returns 500              | Check S3 URI, configured bucket, exact key/case, GetObject/decrypt permissions, size limit, and JSON containing exactly nonempty string `title` and `body`.                             |
| Detail returns 404                             | Use an ID returned by `/api/summary`; the requested ID is absent from the configured table.                                                                                             |
| Fictional summaries still appear               | Stop the preview and use backend `npm start` or the systemd service, not `start:local`.                                                                                                 |
| Wrong API host in browser requests             | Keep `VITE_API_BASE_URL=/api`, check other Vite env files, rebuild React, and reload. Backend env edits do not alter compiled frontend URLs.                                            |
| Works in SSH, fails under systemd              | Check journal logs, absolute Node path, user permissions, built entry point, and environment-file path.                                                                                 |
| Build exits with `Killed` / heap errors        | Check memory and build logs; use an instance with more memory or build compatible artifacts before deploying them.                                                                      |
| HTTP works but HTTPS fails                     | The current application has an HTTP listener on port 3000 and no certificate/HTTPS listener configuration.                                                                              |

For local mock previews, see [README.md](README.md#preview-with-mock-data-no-aws-required).
Implementation details: [backend README](backend/README.md) and [frontend README](frontend/README.md).

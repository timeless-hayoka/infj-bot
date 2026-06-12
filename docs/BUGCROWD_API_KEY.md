# How to Get Your Bugcrowd API Key

## Step 1: Log in to Bugcrowd
Go to https://bugcrowd.com and log in to your researcher account.

## Step 2: Open Profile Settings
1. Click your **avatar/profile picture** (top right corner)
2. Select **"Settings"** or **"Profile"**

## Step 3: Find API Keys
1. Look for a tab or section called:
   - **"API"**
   - **"API Keys"**
   - **"Tokens"**
   - **"Developer"**
   - **"Integrations"**

2. If you don't see it in the main menu, check under:
   - **"Account Settings"** → **"API"**
   - **"Developer Settings"**
   - **"Personal Settings"** → **"API Tokens"**

## Step 4: Generate a New Key
1. Click **"Generate API Key"** or **"Create Token"**
2. Give it a name like "drift-bot"
3. Copy the key immediately (you won't see it again)

## Step 5: Add to DRIFT
Paste it into `/home/crexs/infj_bot/.env`:
```bash
BUGCROWD_API_KEY=your-copied-key-here
```

## Can't Find It?
Bugcrowd sometimes moves this around. Try these direct URLs while logged in:
- https://bugcrowd.com/user/settings/api
- https://bugcrowd.com/settings/api
- https://bugcrowd.com/programs (look for "API" in sidebar)

If you're on a **team/enterprise** account, the admin may need to generate it for you.

# Google Drive Organization Guide

> This guide shows you how to organize all your projects in Google Drive for easy access and sharing.

---

## Recommended Folder Structure

```
My Drive/
└── DRIFT/
    ├── 01_COMPANY/
    │   ├── Incorporation/
    │   │   ├── Delaware_C_Corp_Checklist.pdf
    │   │   ├── Articles_of_Incorporation.pdf
    │   │   ├── EIN_Confirmation.pdf
    │   │   ├── Operating_Agreement.pdf
    │   │   └── IP_Assignment_Agreements.pdf
    │   ├── Legal/
    │   │   ├── Trademark_Application_DRIFT.pdf
    │   │   ├── Copyright_Registration.pdf
    │   │   └── CLA_Signed_Contributors/
    │   ├── Finance/
    │   │   ├── Cap_Table.xlsx
    │   │   ├── SAFE_Notes/
    │   │   ├── Bank_Statements/
    │   │   └── Projections.xlsx
    │   └── Insurance/
    │       └── EO_Insurance.pdf
    │
    ├── 02_PRODUCT/
    │   ├── Code/
    │   │   ├── drift-main.zip (backup of /home/crexs/drift/)
    │   │   ├── infj_bot-private.zip (backup of /home/crexs/infj_bot/)
    │   │   └── Release_Archives/
    │   ├── Documentation/
    │   │   ├── API_Specification.pdf
    │   │   ├── Architecture_Diagrams/
    │   │   └── User_Manual.pdf
    │   ├── Design/
    │   │   ├── Logo_Files/
    │   │   ├── Brand_Guidelines.pdf
    │   │   └── UI_Mockups/
    │   └── Roadmap/
    │       ├── Q2_2026_Goals.md
    │       ├── Q3_2026_Goals.md
    │       └── Feature_Backlog.md
    │
    ├── 03_SALES_MARKETING/
    │   ├── Pitch_Decks/
    │   │   ├── DRIFT_Seed_Pitch_v1.pdf
    │   │   └── DRIFT_Seed_Pitch_v2.pdf
    │   ├── Demos/
    │   │   ├── DRIFT_Demo_Video_2min.mp4
    │   │   └── DRIFT_Demo_Screenshots/
    │   ├── Outreach/
    │   │   ├── Email_Templates/
    │   │   ├── Contact_List.xlsx
    │   │   └── Outreach_Tracking.xlsx
    │   ├── Case_Studies/
    │   │   └── (fill in as you get customers)
    │   └── Press/
    │       ├── Press_Release_Templates/
    │       └── Media_Kit/
    │
    ├── 04_INVESTORS/
    │   ├── Investor_List.xlsx
    │   ├── Pitch_Meetings/
    │   │   ├── 2026-05-10_Replika_Eugenia.md
    │   │   └── (one file per meeting)
    │   ├── Due_Diligence/
    │   │   ├── Financial_Model.xlsx
    │   │   ├── Technical_DD_Responses.pdf
    │   │   └── Cap_Table.xlsx
    │   └── Term_Sheets/
    │       └── (store received term sheets here)
    │
    ├── 05_PERSONAL/
    │   ├── Founder_Agreements/
    │   │   └── (vesting agreements, IP assignment)
    │   ├── Identity/
    │   │   ├── Julien_James_Bio.md
    │   │   ├── Headshots/
    │   │   └── Speaker_Reels/
    │   └── Learning/
    │       ├── Books_and_Courses/
    │       └── Conference_Notes/
    │
    └── 06_ARCHIVE/
        ├── Old_Versions/
        ├── Rejected_Ideas/
        └── Misc/
```

---

## How to Upload Your Projects

### Option 1: Manual Upload (Recommended for now)

1. Go to https://drive.google.com
2. Create folder: `DRIFT`
3. Inside DRIFT, create the subfolders above
4. For each folder, click **New → File upload** or drag-and-drop

### Option 2: Zip and Upload

```bash
# From your terminal
cd /home/crexs

# Zip drift project
zip -r drift-backup-$(date +%Y%m%d).zip drift/ -x "*/__pycache__/*" -x "*/chroma_db/*" -x "*/.git/*"

# Zip infj_bot project (private)
zip -r infj_bot-private-$(date +%Y%m%d).zip infj_bot/ -x "*/__pycache__/*" -x "*/chroma_db/*" -x "*/.git/*" -x "*/.env"

# These zip files are now in /home/crexs/
# Upload them to Google Drive → DRIFT/02_PRODUCT/Code/
```

### Option 3: rclone (Advanced, for ongoing sync)

```bash
# Install rclone
sudo apt-get install rclone

# Configure
rclone config
# Follow prompts to add Google Drive

# Sync drift folder
rclone sync /home/crexs/drift gdrive:DRIFT/02_PRODUCT/Code/drift-main

# Sync infj_bot (private)
rclone sync /home/crexs/infj_bot gdrive:DRIFT/02_PRODUCT/Code/infj_bot-private
```

---

## Critical Files to Back Up FIRST

Priority 1 (do this today):
- [ ] `/home/crexs/infj_bot/` (your original project)
- [ ] `/home/crexs/drift/` (your new commercial project)
- [ ] `/home/crexs/infj_bot/OWNER_PROFILE.md` (your private info)

Priority 2 (this week):
- [ ] Any `.env` files (API keys — store in encrypted vault, not plain Drive)
- [ ] Database files (`.db` files from infj_bot)
- [ ] ChromaDB collections (`chroma_db/` directory)

Priority 3 (ongoing):
- [ ] Pitch decks
- [ ] Demo videos
- [ ] Legal documents

---

## Security Notes

**DO NOT store these in Google Drive unencrypted:**
- API keys (Gemini, etc.)
- Passwords
- Private SSH keys
- Unredacted database dumps with user data

**Instead:**
- Use a password manager (Bitwarden, 1Password)
- Or encrypt files before uploading:
  ```bash
  gpg -c sensitive_file.pdf
  # Upload sensitive_file.pdf.gpg
  ```

---

## Sharing Settings

| Folder | Who to Share With | Permission |
|---|---|---|
| `01_COMPANY/Legal` | Only you + lawyer | Editor |
| `01_COMPANY/Finance` | Only you + accountant | Editor |
| `03_SALES_MARKETING/Pitch_Decks` | Investors, partners | Viewer |
| `03_SALES_MARKETING/Demos` | Public | Viewer (anyone with link) |
| `02_PRODUCT/Documentation` | Team, contributors | Viewer |
| `04_INVESTORS` | Only you | Editor |

---

## Quick Start Checklist

- [ ] Create `DRIFT` folder in Google Drive
- [ ] Create 6 subfolders (01_COMPANY through 06_ARCHIVE)
- [ ] Zip and upload `/home/crexs/drift/`
- [ ] Zip and upload `/home/crexs/infj_bot/`
- [ ] Upload pitch deck to `03_SALES_MARKETING/Pitch_Decks/`
- [ ] Upload demo video to `03_SALES_MARKETING/Demos/`
- [ ] Set sharing permissions appropriately

---

*Back up your work, Julien. 18,000 lines is your life's work — protect it.*

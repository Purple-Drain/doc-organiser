# GitHub Update Instructions

## Step 1: Pull Latest & Create Branch

```bash
cd ~/Projects/doc-organiser
git pull origin main
git checkout -b feature/enhanced-filename-detail
```

## Step 2: Copy Files

Download and replace these files in your project:
- organise_scans.py
- rules.json
- README.md

## Step 3: Commit Changes

```bash
# Check what changed
git status
git diff

# Stage all changes
git add organise_scans.py rules.json README.md

# Commit with message
git commit -m "feat: enhance filename detail with improved metadata extraction

- Add smart title extraction from both filename and document content
- Improve date parsing with 6+ format patterns
- Add party name detection (Aaron/Sylvia) to filenames
- Include original page ranges in split documents
- Enhance generic filename detection
- Update comprehensive README with v3.1 features
- Maintain backward compatibility with existing OID system"

# Push to GitHub
git push origin feature/enhanced-filename-detail
```

## Step 4: Create Pull Request

Using GitHub CLI:
```bash
gh pr create --title "Enhanced Filename Detail v3.1" \
  --body "Improves metadata extraction and filename generation"
gh pr merge --squash
```

Or manually via: https://github.com/Purple-Drain/doc-organiser/pulls

## Step 5: Clean Up

```bash
git checkout main
git pull origin main
git branch -d feature/enhanced-filename-detail
```

Done! 🎉

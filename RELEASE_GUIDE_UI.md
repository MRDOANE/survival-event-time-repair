# GitHub and Zenodo release guide (graphical interface only)

Suggested repository name: `survival-event-time-repair`

Suggested description: “Reproducibility code and results for conformal survival
lower prediction bounds under event-time coarsening.”

## Before uploading

1. Unzip the release archive on your computer.
2. Check the author name and title in `CITATION.cff` and `.zenodo.json`. Add
   your ORCID to both files if desired.
3. Do not add the unfinished faithful-baseline package or any RunPod logs.

## Publish with GitHub Desktop

GitHub's browser uploader is awkward for this repository because it limits each
upload operation to 100 files. GitHub Desktop is still a graphical interface
and preserves the complete directory tree.

1. Install and sign in to [GitHub Desktop](https://desktop.github.com/).
2. Choose **File → Add Local Repository…** and select the extracted
   `survival-event-time-repair-github-v1.0.0` folder.
3. If Desktop says the folder is not yet a Git repository, choose **create a
   repository**, keep the existing files, set the name to
   `survival-event-time-repair`, and choose **None** for license and gitignore
   because both are already included.
4. Review the file list. Enter the summary `Initial Statistics in Medicine
   reproducibility release`, then click **Commit to main**.
5. Click **Publish repository**. Use the same repository name, add the suggested
   description, and clear **Keep this code private** unless an embargo is
   required.
6. Open **View on GitHub** and confirm that `README.md`, `NOVELTY_AUDIT.md`,
   `results/`, and all four `study/` directories are visible.

## Connect Zenodo before making the GitHub release

1. Sign in to [Zenodo](https://zenodo.org/) with GitHub.
2. Open your Zenodo profile menu, choose **GitHub**, and authorize Zenodo if
   prompted.
3. Find `survival-event-time-repair` and switch its archive toggle **On**.
4. Return to GitHub and open the repository's **Releases** page.
5. Click **Draft a new release**. Create tag `v1.0.0` targeting `main`.
6. Use the title `v1.0.0 – Statistics in Medicine reproducibility release`.
7. Paste the release notes below and click **Publish release**.

Suggested release notes:

> Frozen reproducibility release for “Repairing conformal survival lower
> prediction bounds under event-time coarsening.” Includes the completed
> 1,200-trial Gate 3 evidence (`ADVANCE_BOTH`), two complete 500-replicate
> external interval-censored analyses (both formally `NEUTRAL`), source
> snapshots, tests, provenance, and explicit claim boundaries. It excludes the
> unfinished faithful-baseline experiment.

Zenodo should archive the release automatically and issue a version DOI plus a
concept DOI. On the Zenodo record, check the title, creator, description,
version, license, keywords, and related GitHub URL. Use the **version DOI** to
cite this exact release and the **concept DOI** when referring to the evolving
software project.

## Add the DOI without creating a duplicate deposit

1. In GitHub, open `README.md`, click the pencil icon, add the Zenodo DOI badge
   or plain DOI near the title, and commit directly to `main`.
2. Open `CITATION.cff`, click the pencil icon, add the version DOI under `doi`,
   update `date-released`, and commit.
3. Do not create a second manual Zenodo upload for the same v1.0.0 release.
   The GitHub integration already created the archival record.

## If automatic archiving fails

Use the Zenodo web interface only after confirming that no record was created:

1. Choose **Upload → New upload** on Zenodo.
2. Upload the same GitHub release ZIP downloaded from the GitHub Releases page.
3. Select resource type **Software**, enter the title and Michael Doane as
   creator, set version `1.0.0`, license `GPL-3.0-or-later`, and paste the
   repository description and keywords from `.zenodo.json`.
4. Add the GitHub repository URL as a related identifier if the form accepts
   it; use a software/source relationship offered by the UI. It is safe to omit
   this optional field if the UI rejects the URL or relationship.
5. Preview the record, verify every field, then click **Publish** once.

## Manuscript wording

Suggested Data Availability statement after the DOI exists:

> Code, frozen configurations, aggregate and replicate-level results, and the
> data extracts distributed with the source R package are archived at Zenodo
> (DOI: [insert version DOI]). The official DR-COSARC implementation is obtained
> at run time from its public repository at the commit and hashes recorded in
> the archive.

For *Statistics in Medicine*, submit the initial manuscript through Research
Exchange. The journal allows free-format initial submission, encourages a
single manuscript PDF, requires ORCID, and expects public code/data supporting
new methods. The initial manuscript must be authored by the researchers; any
use of generative AI for research or content should be disclosed under the
journal's policy.

## Official help pages

- [Create a GitHub repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)
- [Add files to a GitHub repository](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
- [Create and manage GitHub releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
- [Enable a repository in Zenodo's GitHub integration](https://help.zenodo.org/docs/github/enable-repository/)
- [Archive a GitHub release in Zenodo](https://help.zenodo.org/docs/github/archive-release/)
- [Statistics in Medicine author guidelines](https://onlinelibrary.wiley.com/page/journal/10970258/homepage/forauthors.html)

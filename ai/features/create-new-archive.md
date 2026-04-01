# Simple folder analysis

This feature persists a new archive created by the user and starts the most simple archive / folder analysis, where we
go through all the folders and get some metadata about the folders. You can use the archive_analyzer.py as inspiration,
but keep storage and actual analysing separate. 

## Input

This is just a flow controlling python function. The input variables are: the path of the archive and the name given by 
the user. 

## Expected outputs

A new archive is persisted. 
The analysis of the archive is persisted in the database. This means that for every folder and file, there is an entry
in the database as proposed in the `archive-database-proposition.md`. 

returns nohting is all is well, returns error message in case there is an error. 


## Business rules

- The archive is persisted before the analysis in a separate transaction. We need the archive id for storing the analysis. 
- The simple analysis is persisted in batches if the archive turns out to be big. 
- Folder path cannot be null. Return error that explains
- archive name cannot be null. Return error that explains.
- 

## Components

### CreateArchive
- Flow controlling function
- Takes the parameters
- validates the parameters
- persists archive
- starts simple analysis

### ArchiveRepository
- Persist the archive

### FolderAnalysis
- Does the simple analysis

### FileRepository
- We assume that a folder is a special file
- Persists in batches of 500 
# Archive overview

This feature fetches an overview of all the stored archives so that a user can see the archives that have been added
already. This featuer is called when the archive browser initializes and when a new archive has been added. 

## Input

No particular input.

## Desired results

A list with persisted archives. Each archive has the following properties: 
- id
- name
- date of addition
- analysis status
- amount of files in the archive

## Business rules

- return an empty list when there are no archives yet

## Components


### GetArchives
- Flow controlling function
- Delegates to repository

### ArchiveRepository
- Fetches the archives overview
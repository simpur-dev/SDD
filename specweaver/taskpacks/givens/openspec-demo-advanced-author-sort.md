## ADDED Requirements

### Requirement: User can filter search results by author

The system SHALL provide an author filter on the search page: a select control labelled "Author:" listing "All authors" plus one option per author name present in the current results. Selecting an author SHALL re-fetch results with the Open Library `author` parameter set to that name and reset load-more pagination to the first page. Selecting "All authors" SHALL clear the filter and restore the unfiltered result set.

#### Scenario: Author filter narrows results

- **WHEN** results are displayed and the user selects an author
- **THEN** the grid SHALL show only books whose author matches the selection
- **THEN** pagination SHALL reset to the first page

#### Scenario: Filter cleared

- **WHEN** the user selects "All authors"
- **THEN** the unfiltered result set SHALL be restored

## MODIFIED Requirements

### Requirement: User can sort search results

The system SHALL provide a sort control on the search page that allows the user to order results by relevance (default), newest first, or oldest first. When an author filter is active, sorting SHALL apply to the filtered result set. Changing the author filter SHALL preserve the selected sort and reset pagination; changing the sort SHALL re-fetch the filtered set from the first page.

#### Scenario: Sort composes with the author filter

- **WHEN** an author filter is active and the user changes the sort
- **THEN** the system SHALL re-fetch results with both the author and sort parameters
- **THEN** pagination SHALL reset to the first page of the filtered set

#### Scenario: Filter preserves the selected sort

- **WHEN** a sort other than relevance is selected and the user changes the author filter
- **THEN** the sort selection SHALL remain unchanged
- **THEN** pagination SHALL reset to the first page

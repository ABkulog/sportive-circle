Feature: Clubs
  Only real, active UW clubs, and membership that officers confirm.

  Background:
    Given "Riley" is a Husky
    And "Admin" is an admin

  @FR-CLUB-1
  Scenario: A club's official page, if given, has to be its real UW page
    When "Riley" registers a club with the official page "https://example.com/my-club"
    Then they see "HuskyLink page"

  @FR-CLUB-1 @FR-CLUB-2
  Scenario: A club is hidden until an admin approves it
    When "Riley" registers the club "UW Spikeball Club"
    Then visitors don't see "UW Spikeball Club" in the club list
    When "Admin" approves "UW Spikeball Club"
    Then visitors see "UW Spikeball Club" in the club list

  @FR-CLUB-4 @FR-CLUB-5
  Scenario: You're a member only after an officer confirms you
    Given "Riley" runs the approved club "UW Spikeball Club"
    And "Jordan" is a Husky
    When "Jordan" asks to join "UW Spikeball Club"
    Then "Jordan" is "requested" in "UW Spikeball Club"
    When "Riley" confirms "Jordan" in "UW Spikeball Club"
    Then "Jordan" is "member" in "UW Spikeball Club"
    And "Jordan" sees "Member" next to "UW Spikeball Club" in My clubs

  @FR-CLUB-6
  Scenario: Students can message officers before joining
    Given "Riley" runs the approved club "UW Spikeball Club"
    And "Jordan" is a Husky
    When "Jordan" messages "Riley" "When is practice?"
    Then "Riley" has a message saying "When is practice?"

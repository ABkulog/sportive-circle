Feature: Suggestions
  Students can tell the team what to improve; only admins read it.

  Background:
    Given "Maya" is a Husky
    And "Admin" is an admin

  @FR-INFO-4
  Scenario: A suggestion reaches the admins, with the sender's name
    When "Maya" sends the suggestion "Add a pickleball ladder"
    Then they see "Thank you!"
    When "Admin" opens the suggestions page for admins
    Then they see "Add a pickleball ladder"
    And they see "From Maya"

  @FR-INFO-4
  Scenario: Anonymous suggestions hide the sender
    When "Maya" sends the anonymous suggestion "The map is hard to find"
    And "Admin" opens the suggestions page for admins
    Then they see "The map is hard to find"
    And they see "Anonymous"
    And they don't see "From Maya"

  @FR-INFO-4
  Scenario: Only admins can read suggestions
    When "Maya" opens the suggestions page for admins
    Then they see "This Dawg got lost"

  @FR-INFO-4
  Scenario: You need an account to send a suggestion
    When a visitor opens the suggestions page
    Then they see "Log in"

  @FR-INFO-4 @NFR-SEC-6
  Scenario: Suggestions are limited to 5 an hour
    When "Maya" sends 6 suggestions in a row
    Then they see "You can send more in an hour"

  @FR-INFO-4
  Scenario: Admins only hear about topics 3 different people bring up
    Given "Jordan" is a Husky
    And "Sam" is a Husky
    When "Maya" sends the suggestion "Please add badminton"
    And "Jordan" sends the suggestion "badminton courts pls"
    Then "Admin" has 0 on the Admin icon
    When "Sam" sends the suggestion "We need badminton"
    Then "Admin" has 1 on the Admin icon
    And "Admin" sees "1 suggestion topic is trending" in What's new

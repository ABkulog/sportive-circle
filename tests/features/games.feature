Feature: Games
  Hosting, finding and joining pickup games on campus.

  Background:
    Given "Maya" is a Husky
    And "Jordan" is a Husky

  @FR-EVT-1 @FR-EVT-8
  Scenario: A new game shows up in the feed
    When "Maya" hosts a basketball game tomorrow
    Then "Jordan" sees "Pickup 5v5" in the feed

  @FR-EVT-2
  Scenario: A sport can only be played where it makes sense
    When "Maya" tries to host rowing at "Denny Field"
    Then they see "can't be played at Denny Field"

  @FR-EVT-2
  Scenario Outline: Pickleball can be played where UW students really play it
    When "Maya" hosts pickleball at "<place>"
    Then they see "<tip>"

    Examples:
      | place                                | tip                                        |
      | IMA North Tennis Courts              | Court 12 is for pickleball                 |
      | IMA (Intramural Activities Building) | Indoor pickleball is in Gym B, Thursdays   |
      | Green Lake Park pickleball courts    | next to the Green Lake Community Center    |

  @FR-EVT-2
  Scenario: Pickleball isn't offered where there are no courts
    When "Maya" tries to host pickleball at "Denny Field"
    Then they see "can't be played at Denny Field"

  @FR-EVT-3
  Scenario: A game can't have more than 100 players (hosts pick any number below that)
    When "Maya" tries to host basketball for 300 players
    Then they see "Pick 2 to 100 players"

  @FR-EVT-4
  Scenario: Need players goes to the top of the feed
    When "Maya" posts that she needs 2 more for soccer in 15 minutes
    Then "Jordan" sees "Need 2 more for Soccer" in the feed

  @FR-EVT-14
  Scenario: Skill level is only a label, so anyone can join
    Given "Maya" hosts a Competitive basketball game tomorrow
    When "Jordan" joins Maya's game
    Then they see "You're in"
    And Maya's game has 2 players

  @FR-EVT-16
  Scenario: A pickup game can't last all day
    When "Maya" tries to host a 24-hour Spikeball game
    Then they see "Spikeball events can be at most 6 hours long."

  @FR-EVT-5
  Scenario: A full game can't be overbooked
    Given "Maya" hosts a tennis game for 2 players tomorrow
    And "Jordan" joins Maya's game
    And "Sam" is a Husky
    When "Sam" joins Maya's game
    Then they see "Sorry, this game is full"

  @FR-EVT-5
  Scenario: Leaving frees your spot
    Given "Maya" hosts a tennis game for 2 players tomorrow
    And "Jordan" joins Maya's game
    When "Jordan" leaves Maya's game
    Then Maya's game has 1 player

  @FR-EVT-6
  Scenario: You can't leave a game that's over
    Given "Maya" hosted a basketball game yesterday that "Jordan" played in
    When "Jordan" leaves Maya's game
    Then they see "This game is over"
    And Maya's game has 2 players

  @FR-EVT-7
  Scenario: Canceling a game tells everyone who joined
    Given "Maya" hosts a basketball game tomorrow
    And "Jordan" joins Maya's game
    When "Maya" cancels her game
    Then "jordan@uw.edu" gets an email about "Canceled"
    And "Jordan" sees "Maya canceled Pickup 5v5" in the bell

  @FR-EVT-13
  Scenario: Changing the time tells everyone who joined
    Given "Maya" hosts a basketball game tomorrow
    And "Jordan" joins Maya's game
    When "Maya" moves her game an hour later
    Then "Jordan" has 1 on the Bell icon
    And "Jordan" sees "Maya changed Pickup 5v5: new time" in the bell
    And "jordan@uw.edu" gets an email about "Changed: Pickup 5v5"

  @FR-EVT-13
  Scenario: A small change doesn't send an email
    Given "Maya" hosts a basketball game tomorrow
    And "Jordan" joins Maya's game
    When "Maya" changes the note of her game to "Bring water"
    Then "Jordan" sees "Maya changed Pickup 5v5: new note" in the bell
    And "jordan@uw.edu" gets no email about "Changed"

  @FR-EVT-9
  Scenario: Add a game to your calendar
    Given "Maya" hosts a basketball game tomorrow
    When "Jordan" downloads the calendar file for Maya's game
    Then the calendar file is valid for Seattle time

  @FR-EVT-11
  Scenario: A reminder an hour before
    Given "Maya" hosts a basketball game starting in 45 minutes that "Jordan" joined yesterday
    When the reminder job runs
    Then "jordan@uw.edu" gets an email about "starts in"

  @FR-EVT-12
  Scenario: Only players can use a game's group chat
    Given "Maya" hosts a basketball game tomorrow
    And "Sam" is a Husky
    When "Sam" opens the chat for Maya's game
    Then they see "Join the game to use its chat"

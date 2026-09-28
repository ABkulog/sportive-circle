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
  Scenario: A game can't be bigger than the sport allows
    When "Maya" tries to host basketball for 30 players
    Then they see "at most 10 players"

  @FR-EVT-4
  Scenario: Need players goes to the top of the feed
    When "Maya" posts that she needs 2 more for soccer in 15 minutes
    Then "Jordan" sees "Need 2 more for Soccer" in the feed

  @FR-EVT-10
  Scenario: Skill level is only a label, so anyone can join
    Given "Maya" hosts a Competitive basketball game tomorrow
    When "Jordan" joins Maya's game
    Then they see "You're in"
    And Maya's game has 2 players

  @FR-EVT-5
  Scenario: A full game can't be overbooked
    Given "Maya" hosts a tennis game for 2 players tomorrow
    And "Jordan" joins Maya's game
    And "Sam" is a Husky
    When "Sam" joins Maya's game
    Then they see "Sorry, this event is full"

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
  Scenario: Canceling a game emails everyone who joined
    Given "Maya" hosts a basketball game tomorrow
    And "Jordan" joins Maya's game
    When "Maya" cancels her game
    Then "jordan@uw.edu" gets an email about "Canceled"

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
    Then they see "Join the event to see and send messages"

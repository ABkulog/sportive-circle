Feature: Playing with friends
  From the testers: "Lock can scratch that. I think we do parties." Friends get a "You down?"
  and their spots are held for 30 minutes, so a group can get into a game together.

  Background:
    Given "Maya" is a Husky
    And "Jordan" is a Husky
    And "Sam" is a Husky
    And "Maya" and "Jordan" are friends

  @FR-PARTY-1 @FR-PARTY-2
  Scenario: A friend's spot is held while they decide
    Given "Maya" hosts a tennis game for 2 players tomorrow
    When "Maya" parties up with "Jordan"
    Then "Jordan" sees "Maya wants you in Doubles" in the bell
    When "Sam" joins Maya's game
    Then they see "Sorry, this game is full"
    When "Jordan" says yes to the invite
    Then Maya's game has 2 players

  @FR-PARTY-2
  Scenario: Saying no frees the spot and tells the friend
    Given "Maya" hosts a tennis game for 2 players tomorrow
    And "Maya" parties up with "Jordan"
    When "Jordan" says no to the invite
    And "Sam" joins Maya's game
    Then they see "You're in"
    And "Maya" sees "Jordan can't make Doubles" in the bell

  @FR-PARTY-3
  Scenario: Anyone going can invite friends, not just the host
    Given "Sam" and "Jordan" are friends
    And "Maya" hosts a basketball game tomorrow
    And "Sam" joins Maya's game
    When "Sam" parties up with "Jordan"
    Then "Jordan" sees "Sam wants you in Pickup 5v5" in the bell

  @FR-PRIV-1
  Scenario: A private game needs its password
    Given "Maya" hosts a private basketball game with the password "dawgs26"
    When "Sam" tries to join Maya's game with the password "guess"
    Then they see "That's not the password"
    When "Sam" tries to join Maya's game with the password "dawgs26"
    Then they see "You're in"

  @FR-PRIV-2
  Scenario: Friends you invite to a private game don't need the password
    Given "Maya" hosts a private basketball game with the password "dawgs26"
    And "Maya" parties up with "Jordan"
    When "Jordan" says yes to the invite
    Then Maya's game has 2 players

  @FR-PRIV-3
  Scenario: In a private game, the host says yes to friends other players bring
    Given "Maya" hosts a private basketball game with the password "dawgs26"
    And "Sam" and "Jordan" are friends
    And "Sam" tries to join Maya's game with the password "dawgs26"
    When "Sam" asks to bring "Jordan" with the note "my roommate"
    Then "Maya" sees "Sam wants to bring Jordan to Pickup 5v5: “my roommate”" in the bell
    When "Maya" approves the request for "Jordan"
    And "Jordan" says yes to the invite
    Then Maya's game has 3 players

  @FR-TEAM-1
  Scenario: Team vs team: another group challenges the host's team
    Given "Sam" and "Jordan" are friends
    And "Maya" hosts a 2v2 team game tomorrow
    When "Sam" joins Maya's game
    Then they see "Team games are invite-only"
    When "Sam" challenges Maya's game with "Jordan"
    And "Jordan" says yes to the invite
    Then Maya's game has 3 players
    And "Sam" is on team 2 in Maya's game

  @FR-EVT-15
  Scenario: A group can find games with enough open spots
    Given "Maya" hosts a tennis game for 2 players tomorrow
    Then "Sam" doesn't see "Doubles" in the feed filtered to 5 open spots

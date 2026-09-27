Feature: Ranks
  Ranks keep harder games fun without locking anyone out forever.

  Background:
    Given "Maya" is a Husky
    And "Jordan" is a Husky

  @FR-RANK-1 @FR-RANK-2
  Scenario: Everyone starts at Casual, so Competitive games are locked at first
    When "Maya" tries to host a Competitive basketball game
    Then they see "For players who've reached Competitive"

  @FR-RANK-3
  Scenario: Props after a game
    Given "Maya" hosted a basketball game yesterday that "Jordan" played in
    When "Jordan" gives Maya props
    Then they see "Props sent!"

  @FR-RANK-3
  Scenario: You can't give yourself props
    Given "Maya" hosted a basketball game yesterday that "Jordan" played in
    When "Maya" gives herself props
    Then they see "you can't give yourself props"

  @FR-EVT-4 @FR-RANK-4
  Scenario: A Need players post can have tryout spots
    Given "Maya" is Intermediate in soccer
    When "Maya" posts that she needs 2 more Intermediate players for soccer with 1 tryout spot
    And "Jordan" opens Maya's game
    Then they see "Try out"
    When "Jordan" joins Maya's game
    Then they see "You're in as a tryout"

  @FR-EVT-4 @FR-RANK-4
  Scenario: A Need players post can't have more tryout spots than players needed
    Given "Maya" is Intermediate in soccer
    When "Maya" posts that she needs 1 more Intermediate player for soccer with 2 tryout spots
    Then they see "at most 1 tryout spot"

  @FR-EVT-4 @FR-RANK-5
  Scenario: A Need players host can turn off +1s
    Given "Maya" is Intermediate in soccer
    When "Maya" posts that she needs 2 more Intermediate players for soccer without +1s
    Then Maya's game doesn't allow +1s

  @FR-EVT-4 @FR-RANK-5
  Scenario: Players in a ranked Need players game can bring a friend
    Given "Maya" is Intermediate in soccer
    And "Maya" and "Jordan" are friends
    When "Maya" posts that she needs 2 more Intermediate players for soccer with 0 tryout spots
    And "Maya" opens Maya's game
    Then they see "Bring a friend"

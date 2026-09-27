Feature: Friends and messages
  Find your friends, and keep strangers from spamming you.

  Background:
    Given "Maya Chen" is a Husky
    And "Jordan Rivera" is a Husky

  @FR-SOC-1
  Scenario: Find a friend by searching their name
    When "Jordan Rivera" searches for "maya"
    Then they see "Maya Chen"
    When "Jordan Rivera" sends "Maya Chen" a friend request
    And "Maya Chen" accepts the friend request from "Jordan Rivera"
    Then "Maya Chen" and "Jordan Rivera" are now friends

  @FR-SOC-1
  Scenario: Search works with first and last name
    When "Jordan Rivera" searches for "chen maya"
    Then they see "Maya Chen"

  @FR-SOC-3
  Scenario: Strangers can't message you
    When "Jordan Rivera" messages "Maya Chen" "hey"
    Then "Maya Chen" has no messages

  @FR-SOC-3
  Scenario: Club officers can't message strangers
    Given "Jordan Rivera" runs the approved club "UW Ultimate"
    When "Jordan Rivera" messages "Maya Chen" "join my club!!"
    Then "Maya Chen" has no messages

  @FR-SOC-4
  Scenario: Blocking hides you from search and stops messages
    Given "Maya Chen" and "Jordan Rivera" are friends
    When "Maya Chen" blocks "Jordan Rivera"
    And "Jordan Rivera" searches for "maya"
    Then they don't see "Maya Chen"
    When "Jordan Rivera" messages "Maya Chen" "hello?"
    Then "Maya Chen" has no messages

  @FR-SAFE-1
  Scenario: Report a message
    Given "Maya Chen" and "Jordan Rivera" are friends
    And "Jordan Rivera" messages "Maya Chen" "rude message"
    When "Maya Chen" reports that message as harassment
    Then admins have 1 open report saying "rude message"

Feature: Security and privacy
  The app protects students even when someone tries to misuse it.

  @NFR-SEC-3 @NFR-SEC-7
  Scenario: Pages send security headers and have no inline scripts
    Given "Maya" is a Husky
    When "Maya" opens her own profile
    Then the page has a Content-Security-Policy
    And the page has no inline JavaScript

  @NFR-SEC-3
  Scenario: A name with an apostrophe or HTML can't break the page
    Given "Maya" is a Husky
    And "Liam O'Brien<script>" is a Husky
    And "Maya" and "Liam O'Brien<script>" are friends
    When "Maya" opens Liam's profile
    Then the page shows the name safely

  @NFR-SEC-8
  Scenario: Login can't send you to another website
    Given "Maya" is a Husky
    When "Maya" logs in from a link that points to "//evil.example.com"
    Then they end up on this site

  @NFR-SEC-2
  Scenario: Forms without the security token are refused
    Given "Maya" is a Husky
    When a form is sent without its security token
    Then the request is refused

  @FR-INFO-2 @NFR-LEGAL-1
  Scenario: Privacy and Terms are one tap away
    When a visitor opens the home page
    Then they see "Privacy"
    And they see "Terms"
    And they see "Not an official University of Washington service"

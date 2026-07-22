Feature: Invite a member
  As an organisation owner or admin
  I want to invite people to join my organisation
  So that we can collaborate together

  Rule: Only an owner or admin may invite.  The invite is a pending row
        in the invitations table with a 7-day expiry, and an email is
        sent to the invitee with an accept link.

  Scenario Outline: Happy path invite
    Given organisation "<org>" with "<inviter>" as "<inviter_role>"
    When "<inviter>" invites "<invitee_email>" to "<org>" as "<role>"
    Then an invitation is created with status "pending"
    And the invitation expires 7 days after "<now>"
    And an InvitationSent email event is emitted

    Examples:
      | token  | org       | inviter | inviter_role | invitee_email     | role   | now        | outcome |
      | tok-b  | Acme Corp | alice   | owner        | bob@example.com   | member | 1700000000 | success |
      | tok-c  | Acme Corp | alice   | owner        | carol@example.com | admin  | 1700000000 | success |
      | tok-d  | Acme Corp | admin1  | admin        | dave@example.com  | member | 1700100000 | success |

  Scenario Outline: Non-admin cannot invite
    Given organisation "<org>" with "<inviter>" as "<inviter_role>"
    When "<inviter>" invites "<invitee_email>" to "<org>" as "<role>"
    Then the invite is rejected with code NOT_AUTHORIZED
    And no invitation is created
    And an InviteRejected event is emitted

    Examples:
      | token  | org       | inviter | inviter_role | invitee_email      | role   | now        | outcome                     |
      | tok-e  | Acme Corp | carol   | member       | dave@example.com   | member | 1700000000 | error:NotAuthorizedError    |
      | tok-f  | Personal  | alice   | none         | alice@example.com  | member | 1700000000 | error:NotAuthorizedError    |

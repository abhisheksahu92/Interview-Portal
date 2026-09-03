"""Client portal for staffing firms.

Recruiters register end clients, submit candidates to them, and share expiring
magic-link portals where the client shortlists / rejects / requests interviews.

Integration points for other apps (nothing here needs to be imported to use them):

URL names
    ``clients:index``                 client list
    ``clients:create``                new client
    ``clients:detail`` (pk)           client dashboard: jobs, submissions, links
    ``clients:edit`` (pk)
    ``clients:access_create`` (pk)                    POST: issue + email a link
    ``clients:access_revoke`` (pk, access_id)         POST
    ``clients:access_resend`` (pk, access_id)         POST: rotate token + email
    ``clients:submit_application`` (application_id)   "Submit to client" action
    ``clients:submission_detail`` (pk)                status timeline
    ``clients:job_client`` (job_id)                   set/clear ``Job.client``
    ``clients:portal`` (token)                        client portal, no login
    ``clients:portal_resume`` (token, submission_id)  token-checked resume stream
    ``clients:portal_feedback`` (token, submission_id) POST decision

Templates other apps may include
    ``clients/partials/submit_button.html``  with ``application=<Application>``
    ``clients/partials/status_badge.html``   with ``submission=<Submission>``

Forms other apps may reuse
    ``clients.forms.JobClientForm(company=..., job=...)`` — an "End client" field
    for web/'s job create/edit screens; ``form.apply(job)`` saves it.

Every recruiter-facing view requires the ``client_portal`` entitlement
(``billing.entitlements.require_feature``) plus an OWNER/RECRUITER membership.
"""

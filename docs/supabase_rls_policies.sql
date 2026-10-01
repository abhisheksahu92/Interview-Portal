-- ==========================================================================
-- SUPABASE ROW LEVEL SECURITY (RLS) POLICIES & DEFENSE-IN-DEPTH HARDENING
-- Generated automatically by: python manage.py generate_supabase_rls_sql
-- ==========================================================================

-- 1. Enable RLS on all tables and deny anon / public unauthenticated access
DO $$ BEGIN
  EXECUTE 'ALTER TABLE IF EXISTS "django_admin_log" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "django_admin_log" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "django_admin_log" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "auth_permission" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "auth_permission" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "auth_permission" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "auth_group" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "auth_group" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "auth_group" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "django_content_type" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "django_content_type" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "django_content_type" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "django_session" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "django_session" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "django_session" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "authtoken_token" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "authtoken_token" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "authtoken_token" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "core_company" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "core_company" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "core_company" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "core_user" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "core_user" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "core_user" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "core_membership" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "core_membership" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "core_membership" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "core_invitation" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "core_invitation" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "core_invitation" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "core_cronstate" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "core_cronstate" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "core_cronstate" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "jobs_skill" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "jobs_skill" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "jobs_skill" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "jobs_job" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "jobs_job" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "jobs_job" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "jobs_pipelinestage" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "jobs_pipelinestage" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "jobs_pipelinestage" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "jobs_candidateprofile" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "jobs_candidateprofile" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "jobs_candidateprofile" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "jobs_application" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "jobs_application" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "jobs_application" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "jobs_stagereview" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "jobs_stagereview" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "jobs_stagereview" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "assessments_question" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "assessments_question" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "assessments_question" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "assessments_assessment" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "assessments_assessment" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "assessments_assessment" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "assessments_attempt" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "assessments_attempt" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "assessments_attempt" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_plan" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_plan" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_plan" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_subscription" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_subscription" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_subscription" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_usagerecord" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_usagerecord" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_usagerecord" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_invoice" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_invoice" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_invoice" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_dunningreminder" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_dunningreminder" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_dunningreminder" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_placementfee" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_placementfee" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_placementfee" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_invoicecounter" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_invoicecounter" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_invoicecounter" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_processedwebhookevent" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_processedwebhookevent" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_processedwebhookevent" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_billingcharge" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_billingcharge" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_billingcharge" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "billing_pendingcheckout" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "billing_pendingcheckout" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "billing_pendingcheckout" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "scheduling_intervieweravailability" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "scheduling_intervieweravailability" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "scheduling_intervieweravailability" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "scheduling_calendarconnection" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "scheduling_calendarconnection" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "scheduling_calendarconnection" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "scheduling_interview" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "scheduling_interview" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "scheduling_interview" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "scheduling_interviewslotproposal" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "scheduling_interviewslotproposal" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "scheduling_interviewslotproposal" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "clients_client" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "clients_client" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "clients_client" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "clients_clientaccess" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "clients_clientaccess" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "clients_clientaccess" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "clients_submission" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "clients_submission" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "clients_submission" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "notifications_notificationpreference" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "notifications_notificationpreference" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "notifications_notificationpreference" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "notifications_candidatechanneloptout" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "notifications_candidatechanneloptout" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "notifications_candidatechanneloptout" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "notifications_outboundmessage" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "notifications_outboundmessage" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "notifications_outboundmessage" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "talent_talentprofile" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "talent_talentprofile" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "talent_talentprofile" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "talent_importbatch" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "talent_importbatch" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "talent_importbatch" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "video_videoquestion" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "video_videoquestion" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "video_videoquestion" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "video_videoscreen" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "video_videoscreen" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "video_videoscreen" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "video_videoscreenquestion" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "video_videoscreenquestion" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "video_videoscreenquestion" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "video_videoinvite" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "video_videoinvite" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "video_videoinvite" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "video_videoresponse" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "video_videoresponse" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "video_videoresponse" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "careers_careerssite" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "careers_careerssite" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "careers_careerssite" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "careers_jobdistribution" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "careers_jobdistribution" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "careers_jobdistribution" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "analytics_stagetransition" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "analytics_stagetransition" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "analytics_stagetransition" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "offers_offertemplate" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "offers_offertemplate" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "offers_offertemplate" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "offers_offer" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "offers_offer" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "offers_offer" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "offers_offerevent" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "offers_offerevent" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "offers_offerevent" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "partners_reseller" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "partners_reseller" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "partners_reseller" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "partners_referral" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "partners_referral" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "partners_referral" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "partners_commissionledger" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "partners_commissionledger" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "partners_commissionledger" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "partners_whitelabel" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "partners_whitelabel" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "partners_whitelabel" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "partners_license" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "partners_license" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "partners_license" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "marketplace_questionpack" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "marketplace_questionpack" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "marketplace_questionpack" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "marketplace_packpurchase" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "marketplace_packpurchase" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "marketplace_packpurchase" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "integrations_outboundwebhook" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "integrations_outboundwebhook" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "integrations_outboundwebhook" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "integrations_webhookdelivery" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "integrations_webhookdelivery" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "integrations_webhookdelivery" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "integrations_connectorconfig" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "integrations_connectorconfig" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "integrations_connectorconfig" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "integrations_connectorrun" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "integrations_connectorrun" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "integrations_connectorrun" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "contracting_clientbillingprofile" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "contracting_clientbillingprofile" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "contracting_clientbillingprofile" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "contracting_contractor" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "contracting_contractor" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "contracting_contractor" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "contracting_engagement" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "contracting_engagement" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "contracting_engagement" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "contracting_onboardingdocument" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "contracting_onboardingdocument" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "contracting_onboardingdocument" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "contracting_timesheet" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "contracting_timesheet" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "contracting_timesheet" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "contracting_clientinvoicecounter" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "contracting_clientinvoicecounter" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "contracting_clientinvoicecounter" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "contracting_clientinvoice" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "contracting_clientinvoice" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "contracting_clientinvoice" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "contracting_payrollrun" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "contracting_payrollrun" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "contracting_payrollrun" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "exchange_partnerlink" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "exchange_partnerlink" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "exchange_partnerlink" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "exchange_exchangerequirement" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "exchange_exchangerequirement" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "exchange_exchangerequirement" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "exchange_exchangesubmission" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "exchange_exchangesubmission" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "exchange_exchangesubmission" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "exchange_exchangedeal" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "exchange_exchangedeal" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "exchange_exchangedeal" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "bgv_checkpackage" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "bgv_checkpackage" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "bgv_checkpackage" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "bgv_verificationorder" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "bgv_verificationorder" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "bgv_verificationorder" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "sources_source" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "sources_source" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "sources_source" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "sources_lead" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "sources_lead" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "sources_lead" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "seeker_seekerprofile" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "seeker_seekerprofile" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "seeker_seekerprofile" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "seeker_saveditem" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "seeker_saveditem" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "seeker_saveditem" TO postgres, service_role, authenticated;';
  EXECUTE 'ALTER TABLE IF EXISTS "seeker_outreach" ENABLE ROW LEVEL SECURITY;';
  EXECUTE 'REVOKE ALL ON TABLE "seeker_outreach" FROM anon, public;';
  EXECUTE 'GRANT ALL ON TABLE "seeker_outreach" TO postgres, service_role, authenticated;';
END $$;

-- 2. Create Explicit Access & Tenant Isolation Policies

-- Model: admin.LogEntry (django_admin_log) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_django_admin_log" ON "django_admin_log";
CREATE POLICY "tenant_isolation_django_admin_log" ON "django_admin_log"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: auth.Permission (auth_permission) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_auth_permission" ON "auth_permission";
CREATE POLICY "tenant_isolation_auth_permission" ON "auth_permission"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: auth.Group (auth_group) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_auth_group" ON "auth_group";
CREATE POLICY "tenant_isolation_auth_group" ON "auth_group"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: contenttypes.ContentType (django_content_type) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_django_content_type" ON "django_content_type";
CREATE POLICY "tenant_isolation_django_content_type" ON "django_content_type"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: sessions.Session (django_session) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_django_session" ON "django_session";
CREATE POLICY "tenant_isolation_django_session" ON "django_session"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: authtoken.Token (authtoken_token) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_authtoken_token" ON "authtoken_token";
CREATE POLICY "tenant_isolation_authtoken_token" ON "authtoken_token"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: authtoken.TokenProxy (authtoken_token) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_authtoken_token" ON "authtoken_token";
CREATE POLICY "tenant_isolation_authtoken_token" ON "authtoken_token"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: core.Company (core_company)
DROP POLICY IF EXISTS "tenant_isolation_core_company" ON "core_company";
CREATE POLICY "tenant_isolation_core_company" ON "core_company"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("id"::text = NULLIF(current_setting('app.current_company_id', true), '')
         OR NULLIF(current_setting('app.current_company_id', true), '') IS NULL)
  WITH CHECK ("id"::text = NULLIF(current_setting('app.current_company_id', true), '')
              OR NULLIF(current_setting('app.current_company_id', true), '') IS NULL);

-- Model: core.User (core_user) - Global User Auth & Session Security
DROP POLICY IF EXISTS "tenant_isolation_core_user" ON "core_user";
CREATE POLICY "tenant_isolation_core_user" ON "core_user"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: core.Membership (core_membership) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_core_membership" ON "core_membership";
CREATE POLICY "tenant_isolation_core_membership" ON "core_membership"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: core.Invitation (core_invitation) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_core_invitation" ON "core_invitation";
CREATE POLICY "tenant_isolation_core_invitation" ON "core_invitation"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: core.CronState (core_cronstate) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_core_cronstate" ON "core_cronstate";
CREATE POLICY "tenant_isolation_core_cronstate" ON "core_cronstate"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: jobs.Skill (jobs_skill) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_jobs_skill" ON "jobs_skill";
CREATE POLICY "tenant_isolation_jobs_skill" ON "jobs_skill"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: jobs.Job (jobs_job) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_jobs_job" ON "jobs_job";
CREATE POLICY "tenant_isolation_jobs_job" ON "jobs_job"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: jobs.PipelineStage (jobs_pipelinestage) [Lookup: job__company]
DROP POLICY IF EXISTS "tenant_isolation_jobs_pipelinestage" ON "jobs_pipelinestage";
CREATE POLICY "tenant_isolation_jobs_pipelinestage" ON "jobs_pipelinestage"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "jobs_pipelinestage"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "jobs_pipelinestage"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: jobs.CandidateProfile (jobs_candidateprofile) - Candidate Personal Scope
DROP POLICY IF EXISTS "tenant_isolation_jobs_candidateprofile" ON "jobs_candidateprofile";
CREATE POLICY "tenant_isolation_jobs_candidateprofile" ON "jobs_candidateprofile"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: jobs.Application (jobs_application) [Lookup: job__company]
DROP POLICY IF EXISTS "tenant_isolation_jobs_application" ON "jobs_application";
CREATE POLICY "tenant_isolation_jobs_application" ON "jobs_application"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "jobs_application"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "jobs_application"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: jobs.StageReview (jobs_stagereview) [Lookup: application__job__company]
DROP POLICY IF EXISTS "tenant_isolation_jobs_stagereview" ON "jobs_stagereview";
CREATE POLICY "tenant_isolation_jobs_stagereview" ON "jobs_stagereview"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "jobs_stagereview"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "jobs_stagereview"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: assessments.Question (assessments_question) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_assessments_question" ON "assessments_question";
CREATE POLICY "tenant_isolation_assessments_question" ON "assessments_question"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: assessments.Assessment (assessments_assessment) [Lookup: job__company]
DROP POLICY IF EXISTS "tenant_isolation_assessments_assessment" ON "assessments_assessment";
CREATE POLICY "tenant_isolation_assessments_assessment" ON "assessments_assessment"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "assessments_assessment"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "assessments_assessment"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: assessments.Attempt (assessments_attempt) [Lookup: assessment__job__company]
DROP POLICY IF EXISTS "tenant_isolation_assessments_attempt" ON "assessments_attempt";
CREATE POLICY "tenant_isolation_assessments_attempt" ON "assessments_attempt"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "assessments_assessment" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "assessments_attempt"."assessment_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "assessments_assessment" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "assessments_attempt"."assessment_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: billing.Plan (billing_plan) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_billing_plan" ON "billing_plan";
CREATE POLICY "tenant_isolation_billing_plan" ON "billing_plan"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: billing.Subscription (billing_subscription) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_billing_subscription" ON "billing_subscription";
CREATE POLICY "tenant_isolation_billing_subscription" ON "billing_subscription"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.UsageRecord (billing_usagerecord) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_billing_usagerecord" ON "billing_usagerecord";
CREATE POLICY "tenant_isolation_billing_usagerecord" ON "billing_usagerecord"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.Invoice (billing_invoice) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_billing_invoice" ON "billing_invoice";
CREATE POLICY "tenant_isolation_billing_invoice" ON "billing_invoice"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.DunningReminder (billing_dunningreminder) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_billing_dunningreminder" ON "billing_dunningreminder";
CREATE POLICY "tenant_isolation_billing_dunningreminder" ON "billing_dunningreminder"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: billing.PlacementFee (billing_placementfee) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_billing_placementfee" ON "billing_placementfee";
CREATE POLICY "tenant_isolation_billing_placementfee" ON "billing_placementfee"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.InvoiceCounter (billing_invoicecounter) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_billing_invoicecounter" ON "billing_invoicecounter";
CREATE POLICY "tenant_isolation_billing_invoicecounter" ON "billing_invoicecounter"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: billing.ProcessedWebhookEvent (billing_processedwebhookevent) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_billing_processedwebhookevent" ON "billing_processedwebhookevent";
CREATE POLICY "tenant_isolation_billing_processedwebhookevent" ON "billing_processedwebhookevent"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: billing.BillingCharge (billing_billingcharge) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_billing_billingcharge" ON "billing_billingcharge";
CREATE POLICY "tenant_isolation_billing_billingcharge" ON "billing_billingcharge"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.PendingCheckout (billing_pendingcheckout) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_billing_pendingcheckout" ON "billing_pendingcheckout";
CREATE POLICY "tenant_isolation_billing_pendingcheckout" ON "billing_pendingcheckout"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: scheduling.InterviewerAvailability (scheduling_intervieweravailability) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_scheduling_intervieweravailability" ON "scheduling_intervieweravailability";
CREATE POLICY "tenant_isolation_scheduling_intervieweravailability" ON "scheduling_intervieweravailability"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: scheduling.CalendarConnection (scheduling_calendarconnection) - Candidate Personal Scope
DROP POLICY IF EXISTS "tenant_isolation_scheduling_calendarconnection" ON "scheduling_calendarconnection";
CREATE POLICY "tenant_isolation_scheduling_calendarconnection" ON "scheduling_calendarconnection"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: scheduling.Interview (scheduling_interview) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_scheduling_interview" ON "scheduling_interview";
CREATE POLICY "tenant_isolation_scheduling_interview" ON "scheduling_interview"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: scheduling.InterviewSlotProposal (scheduling_interviewslotproposal) [Lookup: interview__company]
DROP POLICY IF EXISTS "tenant_isolation_scheduling_interviewslotproposal" ON "scheduling_interviewslotproposal";
CREATE POLICY "tenant_isolation_scheduling_interviewslotproposal" ON "scheduling_interviewslotproposal"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "scheduling_interview" AS _t0 WHERE _t0."id" = "scheduling_interviewslotproposal"."interview_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "scheduling_interview" AS _t0 WHERE _t0."id" = "scheduling_interviewslotproposal"."interview_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: clients.Client (clients_client) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_clients_client" ON "clients_client";
CREATE POLICY "tenant_isolation_clients_client" ON "clients_client"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: clients.ClientAccess (clients_clientaccess) [Lookup: client__company]
DROP POLICY IF EXISTS "tenant_isolation_clients_clientaccess" ON "clients_clientaccess";
CREATE POLICY "tenant_isolation_clients_clientaccess" ON "clients_clientaccess"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "clients_client" AS _t0 WHERE _t0."id" = "clients_clientaccess"."client_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "clients_client" AS _t0 WHERE _t0."id" = "clients_clientaccess"."client_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: clients.Submission (clients_submission) [Lookup: application__job__company]
DROP POLICY IF EXISTS "tenant_isolation_clients_submission" ON "clients_submission";
CREATE POLICY "tenant_isolation_clients_submission" ON "clients_submission"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "clients_submission"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "clients_submission"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: notifications.NotificationPreference (notifications_notificationpreference) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_notifications_notificationpreference" ON "notifications_notificationpreference";
CREATE POLICY "tenant_isolation_notifications_notificationpreference" ON "notifications_notificationpreference"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: notifications.CandidateChannelOptOut (notifications_candidatechanneloptout) - Candidate Personal Scope
DROP POLICY IF EXISTS "tenant_isolation_notifications_candidatechanneloptout" ON "notifications_candidatechanneloptout";
CREATE POLICY "tenant_isolation_notifications_candidatechanneloptout" ON "notifications_candidatechanneloptout"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: notifications.OutboundMessage (notifications_outboundmessage) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_notifications_outboundmessage" ON "notifications_outboundmessage";
CREATE POLICY "tenant_isolation_notifications_outboundmessage" ON "notifications_outboundmessage"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: talent.TalentProfile (talent_talentprofile) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_talent_talentprofile" ON "talent_talentprofile";
CREATE POLICY "tenant_isolation_talent_talentprofile" ON "talent_talentprofile"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: talent.ImportBatch (talent_importbatch) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_talent_importbatch" ON "talent_importbatch";
CREATE POLICY "tenant_isolation_talent_importbatch" ON "talent_importbatch"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: video.VideoQuestion (video_videoquestion) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_video_videoquestion" ON "video_videoquestion";
CREATE POLICY "tenant_isolation_video_videoquestion" ON "video_videoquestion"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: video.VideoScreen (video_videoscreen) [Lookup: job__company]
DROP POLICY IF EXISTS "tenant_isolation_video_videoscreen" ON "video_videoscreen";
CREATE POLICY "tenant_isolation_video_videoscreen" ON "video_videoscreen"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "video_videoscreen"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "video_videoscreen"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: video.VideoScreenQuestion (video_videoscreenquestion) [Lookup: screen__job__company]
DROP POLICY IF EXISTS "tenant_isolation_video_videoscreenquestion" ON "video_videoscreenquestion";
CREATE POLICY "tenant_isolation_video_videoscreenquestion" ON "video_videoscreenquestion"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "video_videoscreen" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "video_videoscreenquestion"."screen_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "video_videoscreen" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "video_videoscreenquestion"."screen_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: video.VideoInvite (video_videoinvite) [Lookup: application__job__company]
DROP POLICY IF EXISTS "tenant_isolation_video_videoinvite" ON "video_videoinvite";
CREATE POLICY "tenant_isolation_video_videoinvite" ON "video_videoinvite"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "video_videoinvite"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "video_videoinvite"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: video.VideoResponse (video_videoresponse) [Lookup: invite__application__job__company]
DROP POLICY IF EXISTS "tenant_isolation_video_videoresponse" ON "video_videoresponse";
CREATE POLICY "tenant_isolation_video_videoresponse" ON "video_videoresponse"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "video_videoinvite" AS _t0 JOIN "jobs_application" AS _t1 ON _t1."id" = _t0."application_id" JOIN "jobs_job" AS _t2 ON _t2."id" = _t1."job_id" WHERE _t0."id" = "video_videoresponse"."invite_id" AND _t2."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "video_videoinvite" AS _t0 JOIN "jobs_application" AS _t1 ON _t1."id" = _t0."application_id" JOIN "jobs_job" AS _t2 ON _t2."id" = _t1."job_id" WHERE _t0."id" = "video_videoresponse"."invite_id" AND _t2."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: careers.CareersSite (careers_careerssite) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_careers_careerssite" ON "careers_careerssite";
CREATE POLICY "tenant_isolation_careers_careerssite" ON "careers_careerssite"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: careers.JobDistribution (careers_jobdistribution) [Lookup: job__company]
DROP POLICY IF EXISTS "tenant_isolation_careers_jobdistribution" ON "careers_jobdistribution";
CREATE POLICY "tenant_isolation_careers_jobdistribution" ON "careers_jobdistribution"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "careers_jobdistribution"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_job" AS _t0 WHERE _t0."id" = "careers_jobdistribution"."job_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: analytics.StageTransition (analytics_stagetransition) [Lookup: application__job__company]
DROP POLICY IF EXISTS "tenant_isolation_analytics_stagetransition" ON "analytics_stagetransition";
CREATE POLICY "tenant_isolation_analytics_stagetransition" ON "analytics_stagetransition"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "analytics_stagetransition"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "analytics_stagetransition"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: offers.OfferTemplate (offers_offertemplate) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_offers_offertemplate" ON "offers_offertemplate";
CREATE POLICY "tenant_isolation_offers_offertemplate" ON "offers_offertemplate"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: offers.Offer (offers_offer) [Lookup: application__job__company]
DROP POLICY IF EXISTS "tenant_isolation_offers_offer" ON "offers_offer";
CREATE POLICY "tenant_isolation_offers_offer" ON "offers_offer"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "offers_offer"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "jobs_application" AS _t0 JOIN "jobs_job" AS _t1 ON _t1."id" = _t0."job_id" WHERE _t0."id" = "offers_offer"."application_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: offers.OfferEvent (offers_offerevent) [Lookup: offer__application__job__company]
DROP POLICY IF EXISTS "tenant_isolation_offers_offerevent" ON "offers_offerevent";
CREATE POLICY "tenant_isolation_offers_offerevent" ON "offers_offerevent"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "offers_offer" AS _t0 JOIN "jobs_application" AS _t1 ON _t1."id" = _t0."application_id" JOIN "jobs_job" AS _t2 ON _t2."id" = _t1."job_id" WHERE _t0."id" = "offers_offerevent"."offer_id" AND _t2."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "offers_offer" AS _t0 JOIN "jobs_application" AS _t1 ON _t1."id" = _t0."application_id" JOIN "jobs_job" AS _t2 ON _t2."id" = _t1."job_id" WHERE _t0."id" = "offers_offerevent"."offer_id" AND _t2."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: partners.Reseller (partners_reseller) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_partners_reseller" ON "partners_reseller";
CREATE POLICY "tenant_isolation_partners_reseller" ON "partners_reseller"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: partners.Referral (partners_referral) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_partners_referral" ON "partners_referral";
CREATE POLICY "tenant_isolation_partners_referral" ON "partners_referral"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: partners.CommissionLedger (partners_commissionledger) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_partners_commissionledger" ON "partners_commissionledger";
CREATE POLICY "tenant_isolation_partners_commissionledger" ON "partners_commissionledger"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: partners.WhiteLabel (partners_whitelabel) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_partners_whitelabel" ON "partners_whitelabel";
CREATE POLICY "tenant_isolation_partners_whitelabel" ON "partners_whitelabel"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: partners.License (partners_license) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_partners_license" ON "partners_license";
CREATE POLICY "tenant_isolation_partners_license" ON "partners_license"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: marketplace.QuestionPack (marketplace_questionpack) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_marketplace_questionpack" ON "marketplace_questionpack";
CREATE POLICY "tenant_isolation_marketplace_questionpack" ON "marketplace_questionpack"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: marketplace.PackPurchase (marketplace_packpurchase) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_marketplace_packpurchase" ON "marketplace_packpurchase";
CREATE POLICY "tenant_isolation_marketplace_packpurchase" ON "marketplace_packpurchase"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: integrations.OutboundWebhook (integrations_outboundwebhook) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_integrations_outboundwebhook" ON "integrations_outboundwebhook";
CREATE POLICY "tenant_isolation_integrations_outboundwebhook" ON "integrations_outboundwebhook"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: integrations.WebhookDelivery (integrations_webhookdelivery) [Lookup: webhook__company]
DROP POLICY IF EXISTS "tenant_isolation_integrations_webhookdelivery" ON "integrations_webhookdelivery";
CREATE POLICY "tenant_isolation_integrations_webhookdelivery" ON "integrations_webhookdelivery"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "integrations_outboundwebhook" AS _t0 WHERE _t0."id" = "integrations_webhookdelivery"."webhook_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "integrations_outboundwebhook" AS _t0 WHERE _t0."id" = "integrations_webhookdelivery"."webhook_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: integrations.ConnectorConfig (integrations_connectorconfig) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_integrations_connectorconfig" ON "integrations_connectorconfig";
CREATE POLICY "tenant_isolation_integrations_connectorconfig" ON "integrations_connectorconfig"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: integrations.ConnectorRun (integrations_connectorrun) [Lookup: config__company]
DROP POLICY IF EXISTS "tenant_isolation_integrations_connectorrun" ON "integrations_connectorrun";
CREATE POLICY "tenant_isolation_integrations_connectorrun" ON "integrations_connectorrun"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "integrations_connectorconfig" AS _t0 WHERE _t0."id" = "integrations_connectorrun"."config_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "integrations_connectorconfig" AS _t0 WHERE _t0."id" = "integrations_connectorrun"."config_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: contracting.ClientBillingProfile (contracting_clientbillingprofile) [Lookup: client__company]
DROP POLICY IF EXISTS "tenant_isolation_contracting_clientbillingprofile" ON "contracting_clientbillingprofile";
CREATE POLICY "tenant_isolation_contracting_clientbillingprofile" ON "contracting_clientbillingprofile"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "clients_client" AS _t0 WHERE _t0."id" = "contracting_clientbillingprofile"."client_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "clients_client" AS _t0 WHERE _t0."id" = "contracting_clientbillingprofile"."client_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: contracting.Contractor (contracting_contractor) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_contracting_contractor" ON "contracting_contractor";
CREATE POLICY "tenant_isolation_contracting_contractor" ON "contracting_contractor"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: contracting.Engagement (contracting_engagement) [Lookup: contractor__company]
DROP POLICY IF EXISTS "tenant_isolation_contracting_engagement" ON "contracting_engagement";
CREATE POLICY "tenant_isolation_contracting_engagement" ON "contracting_engagement"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "contracting_contractor" AS _t0 WHERE _t0."id" = "contracting_engagement"."contractor_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "contracting_contractor" AS _t0 WHERE _t0."id" = "contracting_engagement"."contractor_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: contracting.OnboardingDocument (contracting_onboardingdocument) [Lookup: contractor__company]
DROP POLICY IF EXISTS "tenant_isolation_contracting_onboardingdocument" ON "contracting_onboardingdocument";
CREATE POLICY "tenant_isolation_contracting_onboardingdocument" ON "contracting_onboardingdocument"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "contracting_contractor" AS _t0 WHERE _t0."id" = "contracting_onboardingdocument"."contractor_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "contracting_contractor" AS _t0 WHERE _t0."id" = "contracting_onboardingdocument"."contractor_id" AND _t0."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: contracting.Timesheet (contracting_timesheet) [Lookup: engagement__contractor__company]
DROP POLICY IF EXISTS "tenant_isolation_contracting_timesheet" ON "contracting_timesheet";
CREATE POLICY "tenant_isolation_contracting_timesheet" ON "contracting_timesheet"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (EXISTS (SELECT 1 FROM "contracting_engagement" AS _t0 JOIN "contracting_contractor" AS _t1 ON _t1."id" = _t0."contractor_id" WHERE _t0."id" = "contracting_timesheet"."engagement_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK (EXISTS (SELECT 1 FROM "contracting_engagement" AS _t0 JOIN "contracting_contractor" AS _t1 ON _t1."id" = _t0."contractor_id" WHERE _t0."id" = "contracting_timesheet"."engagement_id" AND _t1."company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: contracting.ClientInvoiceCounter (contracting_clientinvoicecounter) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_contracting_clientinvoicecounter" ON "contracting_clientinvoicecounter";
CREATE POLICY "tenant_isolation_contracting_clientinvoicecounter" ON "contracting_clientinvoicecounter"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: contracting.ClientInvoice (contracting_clientinvoice) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_contracting_clientinvoice" ON "contracting_clientinvoice";
CREATE POLICY "tenant_isolation_contracting_clientinvoice" ON "contracting_clientinvoice"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: contracting.PayrollRun (contracting_payrollrun) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_contracting_payrollrun" ON "contracting_payrollrun";
CREATE POLICY "tenant_isolation_contracting_payrollrun" ON "contracting_payrollrun"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: exchange.PartnerLink (exchange_partnerlink) [Lookup: from_company]
DROP POLICY IF EXISTS "tenant_isolation_exchange_partnerlink" ON "exchange_partnerlink";
CREATE POLICY "tenant_isolation_exchange_partnerlink" ON "exchange_partnerlink"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("from_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("from_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: exchange.ExchangeRequirement (exchange_exchangerequirement) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_exchange_exchangerequirement" ON "exchange_exchangerequirement";
CREATE POLICY "tenant_isolation_exchange_exchangerequirement" ON "exchange_exchangerequirement"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: exchange.ExchangeSubmission (exchange_exchangesubmission) [Lookup: responding_company]
DROP POLICY IF EXISTS "tenant_isolation_exchange_exchangesubmission" ON "exchange_exchangesubmission";
CREATE POLICY "tenant_isolation_exchange_exchangesubmission" ON "exchange_exchangesubmission"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("responding_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("responding_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: exchange.ExchangeDeal (exchange_exchangedeal) - Default Authenticated Access
DROP POLICY IF EXISTS "tenant_isolation_exchange_exchangedeal" ON "exchange_exchangedeal";
CREATE POLICY "tenant_isolation_exchange_exchangedeal" ON "exchange_exchangedeal"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: bgv.CheckPackage (bgv_checkpackage) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_bgv_checkpackage" ON "bgv_checkpackage";
CREATE POLICY "tenant_isolation_bgv_checkpackage" ON "bgv_checkpackage"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: bgv.VerificationOrder (bgv_verificationorder) [Lookup: company]
DROP POLICY IF EXISTS "tenant_isolation_bgv_verificationorder" ON "bgv_verificationorder";
CREATE POLICY "tenant_isolation_bgv_verificationorder" ON "bgv_verificationorder"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: sources.Source (sources_source) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_sources_source" ON "sources_source";
CREATE POLICY "tenant_isolation_sources_source" ON "sources_source"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: sources.Lead (sources_lead) - Global Shared/System Table
DROP POLICY IF EXISTS "tenant_isolation_sources_lead" ON "sources_lead";
CREATE POLICY "tenant_isolation_sources_lead" ON "sources_lead"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: seeker.SeekerProfile (seeker_seekerprofile) - Candidate Personal Scope
DROP POLICY IF EXISTS "tenant_isolation_seeker_seekerprofile" ON "seeker_seekerprofile";
CREATE POLICY "tenant_isolation_seeker_seekerprofile" ON "seeker_seekerprofile"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: seeker.SavedItem (seeker_saveditem) - Candidate Personal Scope
DROP POLICY IF EXISTS "tenant_isolation_seeker_saveditem" ON "seeker_saveditem";
CREATE POLICY "tenant_isolation_seeker_saveditem" ON "seeker_saveditem"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

-- Model: seeker.Outreach (seeker_outreach) - Candidate Personal Scope
DROP POLICY IF EXISTS "tenant_isolation_seeker_outreach" ON "seeker_outreach";
CREATE POLICY "tenant_isolation_seeker_outreach" ON "seeker_outreach"
  FOR ALL
  TO authenticated, service_role, postgres
  USING (TRUE)
  WITH CHECK (TRUE);

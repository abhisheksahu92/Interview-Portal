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

-- 2. Create Tenant Isolation Policies based on app.current_company_id session context

-- Model: core.User (core_user)
DROP POLICY IF EXISTS "tenant_isolation_core_user" ON "core_user";
CREATE POLICY "tenant_isolation_core_user" ON "core_user"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("last_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("last_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: core.Membership (core_membership)
DROP POLICY IF EXISTS "tenant_isolation_core_membership" ON "core_membership";
CREATE POLICY "tenant_isolation_core_membership" ON "core_membership"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: core.Invitation (core_invitation)
DROP POLICY IF EXISTS "tenant_isolation_core_invitation" ON "core_invitation";
CREATE POLICY "tenant_isolation_core_invitation" ON "core_invitation"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: jobs.Skill (jobs_skill)
DROP POLICY IF EXISTS "tenant_isolation_jobs_skill" ON "jobs_skill";
CREATE POLICY "tenant_isolation_jobs_skill" ON "jobs_skill"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: jobs.Job (jobs_job)
DROP POLICY IF EXISTS "tenant_isolation_jobs_job" ON "jobs_job";
CREATE POLICY "tenant_isolation_jobs_job" ON "jobs_job"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: jobs.PipelineStage (jobs_pipelinestage) via Job
DROP POLICY IF EXISTS "tenant_isolation_jobs_pipelinestage" ON "jobs_pipelinestage";
CREATE POLICY "tenant_isolation_jobs_pipelinestage" ON "jobs_pipelinestage"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: jobs.Application (jobs_application) via Job
DROP POLICY IF EXISTS "tenant_isolation_jobs_application" ON "jobs_application";
CREATE POLICY "tenant_isolation_jobs_application" ON "jobs_application"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: assessments.Question (assessments_question)
DROP POLICY IF EXISTS "tenant_isolation_assessments_question" ON "assessments_question";
CREATE POLICY "tenant_isolation_assessments_question" ON "assessments_question"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: assessments.Assessment (assessments_assessment) via Job
DROP POLICY IF EXISTS "tenant_isolation_assessments_assessment" ON "assessments_assessment";
CREATE POLICY "tenant_isolation_assessments_assessment" ON "assessments_assessment"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: billing.Subscription (billing_subscription)
DROP POLICY IF EXISTS "tenant_isolation_billing_subscription" ON "billing_subscription";
CREATE POLICY "tenant_isolation_billing_subscription" ON "billing_subscription"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.UsageRecord (billing_usagerecord)
DROP POLICY IF EXISTS "tenant_isolation_billing_usagerecord" ON "billing_usagerecord";
CREATE POLICY "tenant_isolation_billing_usagerecord" ON "billing_usagerecord"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.Invoice (billing_invoice)
DROP POLICY IF EXISTS "tenant_isolation_billing_invoice" ON "billing_invoice";
CREATE POLICY "tenant_isolation_billing_invoice" ON "billing_invoice"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.PlacementFee (billing_placementfee)
DROP POLICY IF EXISTS "tenant_isolation_billing_placementfee" ON "billing_placementfee";
CREATE POLICY "tenant_isolation_billing_placementfee" ON "billing_placementfee"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.BillingCharge (billing_billingcharge)
DROP POLICY IF EXISTS "tenant_isolation_billing_billingcharge" ON "billing_billingcharge";
CREATE POLICY "tenant_isolation_billing_billingcharge" ON "billing_billingcharge"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: billing.PendingCheckout (billing_pendingcheckout)
DROP POLICY IF EXISTS "tenant_isolation_billing_pendingcheckout" ON "billing_pendingcheckout";
CREATE POLICY "tenant_isolation_billing_pendingcheckout" ON "billing_pendingcheckout"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: scheduling.InterviewerAvailability (scheduling_intervieweravailability)
DROP POLICY IF EXISTS "tenant_isolation_scheduling_intervieweravailability" ON "scheduling_intervieweravailability";
CREATE POLICY "tenant_isolation_scheduling_intervieweravailability" ON "scheduling_intervieweravailability"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: scheduling.Interview (scheduling_interview)
DROP POLICY IF EXISTS "tenant_isolation_scheduling_interview" ON "scheduling_interview";
CREATE POLICY "tenant_isolation_scheduling_interview" ON "scheduling_interview"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: clients.Client (clients_client)
DROP POLICY IF EXISTS "tenant_isolation_clients_client" ON "clients_client";
CREATE POLICY "tenant_isolation_clients_client" ON "clients_client"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: notifications.NotificationPreference (notifications_notificationpreference)
DROP POLICY IF EXISTS "tenant_isolation_notifications_notificationpreference" ON "notifications_notificationpreference";
CREATE POLICY "tenant_isolation_notifications_notificationpreference" ON "notifications_notificationpreference"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: notifications.OutboundMessage (notifications_outboundmessage)
DROP POLICY IF EXISTS "tenant_isolation_notifications_outboundmessage" ON "notifications_outboundmessage";
CREATE POLICY "tenant_isolation_notifications_outboundmessage" ON "notifications_outboundmessage"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: talent.TalentProfile (talent_talentprofile)
DROP POLICY IF EXISTS "tenant_isolation_talent_talentprofile" ON "talent_talentprofile";
CREATE POLICY "tenant_isolation_talent_talentprofile" ON "talent_talentprofile"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: talent.ImportBatch (talent_importbatch)
DROP POLICY IF EXISTS "tenant_isolation_talent_importbatch" ON "talent_importbatch";
CREATE POLICY "tenant_isolation_talent_importbatch" ON "talent_importbatch"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: video.VideoQuestion (video_videoquestion)
DROP POLICY IF EXISTS "tenant_isolation_video_videoquestion" ON "video_videoquestion";
CREATE POLICY "tenant_isolation_video_videoquestion" ON "video_videoquestion"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: video.VideoScreen (video_videoscreen) via Job
DROP POLICY IF EXISTS "tenant_isolation_video_videoscreen" ON "video_videoscreen";
CREATE POLICY "tenant_isolation_video_videoscreen" ON "video_videoscreen"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: careers.CareersSite (careers_careerssite)
DROP POLICY IF EXISTS "tenant_isolation_careers_careerssite" ON "careers_careerssite";
CREATE POLICY "tenant_isolation_careers_careerssite" ON "careers_careerssite"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: careers.JobDistribution (careers_jobdistribution) via Job
DROP POLICY IF EXISTS "tenant_isolation_careers_jobdistribution" ON "careers_jobdistribution";
CREATE POLICY "tenant_isolation_careers_jobdistribution" ON "careers_jobdistribution"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')))
  WITH CHECK ("job_id" IN (SELECT id FROM "jobs_job" WHERE "company_id"::text = NULLIF(current_setting('app.current_company_id', true), '')));

-- Model: offers.OfferTemplate (offers_offertemplate)
DROP POLICY IF EXISTS "tenant_isolation_offers_offertemplate" ON "offers_offertemplate";
CREATE POLICY "tenant_isolation_offers_offertemplate" ON "offers_offertemplate"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: partners.Referral (partners_referral)
DROP POLICY IF EXISTS "tenant_isolation_partners_referral" ON "partners_referral";
CREATE POLICY "tenant_isolation_partners_referral" ON "partners_referral"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: partners.CommissionLedger (partners_commissionledger)
DROP POLICY IF EXISTS "tenant_isolation_partners_commissionledger" ON "partners_commissionledger";
CREATE POLICY "tenant_isolation_partners_commissionledger" ON "partners_commissionledger"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: partners.WhiteLabel (partners_whitelabel)
DROP POLICY IF EXISTS "tenant_isolation_partners_whitelabel" ON "partners_whitelabel";
CREATE POLICY "tenant_isolation_partners_whitelabel" ON "partners_whitelabel"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: partners.License (partners_license)
DROP POLICY IF EXISTS "tenant_isolation_partners_license" ON "partners_license";
CREATE POLICY "tenant_isolation_partners_license" ON "partners_license"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: marketplace.PackPurchase (marketplace_packpurchase)
DROP POLICY IF EXISTS "tenant_isolation_marketplace_packpurchase" ON "marketplace_packpurchase";
CREATE POLICY "tenant_isolation_marketplace_packpurchase" ON "marketplace_packpurchase"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: integrations.OutboundWebhook (integrations_outboundwebhook)
DROP POLICY IF EXISTS "tenant_isolation_integrations_outboundwebhook" ON "integrations_outboundwebhook";
CREATE POLICY "tenant_isolation_integrations_outboundwebhook" ON "integrations_outboundwebhook"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: integrations.ConnectorConfig (integrations_connectorconfig)
DROP POLICY IF EXISTS "tenant_isolation_integrations_connectorconfig" ON "integrations_connectorconfig";
CREATE POLICY "tenant_isolation_integrations_connectorconfig" ON "integrations_connectorconfig"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: contracting.Contractor (contracting_contractor)
DROP POLICY IF EXISTS "tenant_isolation_contracting_contractor" ON "contracting_contractor";
CREATE POLICY "tenant_isolation_contracting_contractor" ON "contracting_contractor"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: contracting.ClientInvoiceCounter (contracting_clientinvoicecounter)
DROP POLICY IF EXISTS "tenant_isolation_contracting_clientinvoicecounter" ON "contracting_clientinvoicecounter";
CREATE POLICY "tenant_isolation_contracting_clientinvoicecounter" ON "contracting_clientinvoicecounter"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: contracting.ClientInvoice (contracting_clientinvoice)
DROP POLICY IF EXISTS "tenant_isolation_contracting_clientinvoice" ON "contracting_clientinvoice";
CREATE POLICY "tenant_isolation_contracting_clientinvoice" ON "contracting_clientinvoice"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: contracting.PayrollRun (contracting_payrollrun)
DROP POLICY IF EXISTS "tenant_isolation_contracting_payrollrun" ON "contracting_payrollrun";
CREATE POLICY "tenant_isolation_contracting_payrollrun" ON "contracting_payrollrun"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: exchange.PartnerLink (exchange_partnerlink)
DROP POLICY IF EXISTS "tenant_isolation_exchange_partnerlink" ON "exchange_partnerlink";
CREATE POLICY "tenant_isolation_exchange_partnerlink" ON "exchange_partnerlink"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("from_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("from_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: exchange.ExchangeRequirement (exchange_exchangerequirement)
DROP POLICY IF EXISTS "tenant_isolation_exchange_exchangerequirement" ON "exchange_exchangerequirement";
CREATE POLICY "tenant_isolation_exchange_exchangerequirement" ON "exchange_exchangerequirement"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: exchange.ExchangeSubmission (exchange_exchangesubmission)
DROP POLICY IF EXISTS "tenant_isolation_exchange_exchangesubmission" ON "exchange_exchangesubmission";
CREATE POLICY "tenant_isolation_exchange_exchangesubmission" ON "exchange_exchangesubmission"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("responding_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("responding_company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

-- Model: bgv.VerificationOrder (bgv_verificationorder)
DROP POLICY IF EXISTS "tenant_isolation_bgv_verificationorder" ON "bgv_verificationorder";
CREATE POLICY "tenant_isolation_bgv_verificationorder" ON "bgv_verificationorder"
  FOR ALL
  TO authenticated, service_role, postgres
  USING ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''))
  WITH CHECK ("company_id"::text = NULLIF(current_setting('app.current_company_id', true), ''));

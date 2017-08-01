from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from django.contrib.sites.shortcuts import get_current_site
from django.shortcuts import get_object_or_404
from django.db.models import Q, Prefetch

from core.views.mixins import SuperUserCheckMixin
from ..models import Organization, Project, OrganizationRole, ProjectRole
from questionnaires.models import Questionnaire


class OrganizationMixin:
    """Provide lookup method for the current organization."""

    def get_organization(self, lookup_kwarg='slug'):
        if lookup_kwarg == 'slug' and hasattr(self, 'org_lookup'):
            lookup_kwarg = self.org_lookup
        if not hasattr(self, 'org'):
            self.org = get_object_or_404(Organization,
                                         slug=self.kwargs[lookup_kwarg])
        return self.org


class OrganizationRoles(OrganizationMixin):
    """Provide queryset and serializer context for organization users."""

    lookup_field = 'username'
    org_lookup = 'organization'

    def get_queryset(self):
        self.org = self.get_organization()
        return self.org.users.all()

    def get_serializer_context(self, *args, **kwargs):
        context = super(OrganizationRoles, self).get_serializer_context(
            *args, **kwargs)
        context['organization'] = self.get_organization()
        context['domain'] = get_current_site(self.request).domain
        context['sitename'] = settings.SITE_NAME
        return context


class ProjectMixin:
    """Provide project related methods, properties and context variables.

       Provides methods for access to:
       - Current project
       - Current organization
       - Users organization and/or project roles
       - `is_administrator` class attribute
       - `is_project_member` context variable
       - `form_lang_default` and `form_langs` context variables
    """

    def get_project(self):
        if not hasattr(self, 'prj'):
            self.prj = get_object_or_404(
                Project.objects.select_related('organization'),
                organization__slug=self.kwargs['organization'],
                slug=self.kwargs['project']
            )
        return self.prj

    def get_organization(self):
        if not hasattr(self, '_org'):
            self._org = self.get_project().organization
        return self._org

    def get_org_role(self):
        if not hasattr(self, '_org_role'):
            try:
                self._org_role = OrganizationRole.objects.get(
                    organization=self.get_project().organization,
                    user=self.request.user
                )
            except OrganizationRole.DoesNotExist:
                return None

        return self._org_role

    def get_prj_role(self):
        if self.request.user.is_anonymous:
            return None

        if not hasattr(self, '_prj_role'):
            try:
                self._prj_role = ProjectRole.objects.get(
                    project=self.get_project(),
                    user=self.request.user
                )
            except ProjectRole.DoesNotExist:
                return None

        return self._prj_role

    @property
    def is_administrator(self):
        if not hasattr(self, '_is_admin'):
            self._is_admin = False

            # Check if the user is anonymous: not an admin
            if isinstance(self.request.user, AnonymousUser):
                return False

            # Check if the user is a superuser: is an admin
            if self.is_superuser:
                self._is_admin = True
                return self._is_admin

            # Check if the user has the organization admin role: is an admin
            org_role = self.get_org_role()
            if org_role and org_role.admin:
                self._is_admin = True
                return self._is_admin

            # Check if the user has the project manager role: is an admin
            prj_role = self.get_prj_role()
            if prj_role and prj_role.role == 'PM':
                self._is_admin = True
                return self._is_admin

        return self._is_admin

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        prj_member = self.is_administrator or self.get_prj_role() is not None
        context['is_project_member'] = prj_member

        project = self.get_project()
        if project.current_questionnaire:
            q = Questionnaire.objects.get(id=project.current_questionnaire)
            context['form_lang_default'] = q.default_language

            question = q.questions.filter(~Q(label_xlat={})).first()
            if (question and isinstance(question.label_xlat, dict)):
                form_langs = [(l, settings.FORM_LANGS.get(l))
                              for l in question.label_xlat.keys()]
                context['form_langs'] = sorted(form_langs, key=lambda x: x[1])

        return context


class ProjectRoles(ProjectMixin):
    """Determin organization and project roles for the current user.

       Used in `ProjectUsers` and `ProjectUsersDetail` api views.
    """

    lookup_field = 'username'

    def get_queryset(self):
        self.prj = self.get_project()
        org = self.prj.organization
        orgs = Prefetch(
            'organizationrole_set',
            queryset=OrganizationRole.objects.filter(organization=org))
        prjs = Prefetch(
            'projectrole_set',
            queryset=ProjectRole.objects.filter(project=self.prj))
        return org.users.prefetch_related(orgs, prjs)

    def get_serializer_context(self, *args, **kwargs):
        context = super(ProjectRoles, self).get_serializer_context(
            *args, **kwargs)
        context['project'] = self.get_project()

        return context


class ProjectQuerySetMixin:
    def get_queryset(self):
        if self.request.user.is_superuser:
            return Project.objects.all()

        if hasattr(self.request.user, 'organizations'):
            orgs = self.request.user.organizations.all()
            if len(orgs) > 0:
                return Project.objects.filter(
                    Q(access='public') | Q(organization__in=orgs)
                )

        return Project.objects.filter(access='public')


class ProjectAdminCheckMixin(SuperUserCheckMixin):
    """Determine if user is a project administrator.

       Adds a set of context variables which determine the available
       actions the user is allowed to perform using the UI.
    """

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['is_administrator'] = self.is_administrator
        user = self.request.user
        permissions_contexts = (
            ('party.create', 'is_allowed_add_party'),
            ('spatial.create', 'is_allowed_add_location'),
            ('resource.add', 'is_allowed_add_resource'),
            ('project.import', 'is_allowed_import'),
            ('project.export', 'is_allowed_download'),
        )
        project = self.get_project()
        if not hasattr(self, '_roles'):
            # delegate permission check to tutelary backend
            # remove this when tutelary is removed
            for permission_context in permissions_contexts:
                context[permission_context[1]] = user.has_perm(
                    permission_context[0], project
                )
            return context
        else:
            # check permissions against role permissions
            for permission_context in permissions_contexts:
                context[permission_context[1]] = (
                    permission_context[0] in
                    self.permissions or self.is_administrator)
            return context


class ProjectCreateCheckMixin:
    """Determine if the user is allowed to add project.

       Adds an `add_allowed` context variable. User can either add a project
       to the current organization if they have permissions, or
       can add a project if they have permissions on any other organization of
       which they are a member.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_allow = None

    @property
    def add_allowed(self):
        if self.add_allow is None:
            if (hasattr(self, 'project_create_check_multiple') and
               self.project_create_check_multiple):
                self.add_allow = self.add_allowed_multiple()
            else:
                self.add_allow = self.add_allowed_single()
            self.add_allow = self.add_allow or self.is_superuser
        return self.add_allow

    def add_allowed_single(self):
        return 'project.create' in self.permissions

    def add_allowed_multiple(self):
        chk = False
        if Organization.objects.exists():
            user = self.request.user
            if hasattr(user, 'organizationrole_set'):
                org_roles = user.organizationrole_set.all()
                ids = (org_roles.filter(
                    group__permissions__codename__in=['project.create'])
                    .values_list('organization', flat=True))
                chk = True if ids else False
        return chk

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['add_allowed'] = self.add_allowed
        return context


class OrganizationListMixin:
    """Provide filtered lists of organizations for default and api views.

       Add's a `get_filtered_queryset` method which returns a filtered
       queryset containing all orgaizations the current user has access to.
    """

    def get_filtered_queryset(self, actions=None):
        user = self.request.user
        default = Q(access='public', archived=False)
        all_orgs = Organization.objects.all()
        if user.is_superuser:
            return all_orgs
        if user.is_anonymous:
            return all_orgs.filter(default)

        org_roles = (user.organizationrole_set.all()
                     .select_related('organization'))
        ids = []
        ids += (org_roles.filter(
                organization__access='private', organization__archived=False,
                group__permissions__codename__in=('org.view.private',))
                .values_list('organization', flat=True))
        ids += (org_roles.filter(
                organization__archived=True,
                group__permissions__codename__in=('org.view.archived',))
                .values_list('organization', flat=True))

        query = default | Q(id__in=set(ids))
        return all_orgs.filter(query)


class ProjectListMixin:
    """Provide filtered lists of projects for default and api views.

       Add's a `get_filtered_queryset` method which returns a filtered
       queryset containing all projects the current user has access to based
       on the user's current organization and project roles.
    """

    def get_filtered_queryset(self):
        user = self.request.user
        default = Q(access='public', archived=False)
        all_projects = Project.objects.select_related('organization')
        if user.is_superuser:
            return all_projects
        if user.is_anonymous:
            return all_projects.filter(default)

        org_roles = (user.organizationrole_set.select_related('organization'))
        ids = []
        ids += (org_roles.filter(
                organization__projects__access='private',
                organization__projects__archived=False,
                group__permissions__codename__in=['project.view.private'])
                .values_list('organization__projects', flat=True))
        ids += (org_roles.filter(
                organization__projects__archived=True,
                group__permissions__codename__in=['project.view.archived'])
                .values_list('organization__projects', flat=True))

        prj_roles = user.projectrole_set.select_related('project')
        # public archived
        ids += prj_roles.filter(project__archived=True,
                                project__access='public',
                                project__extent__isnull=False,
                                group__permissions__codename__in=[
                                    'project.view.archived',
                                    'project.view']
                                ).values_list('project', flat=True)

        # private active projects
        ids += prj_roles.filter(project__access='private',
                                project__archived=False,
                                project__extent__isnull=False,
                                group__permissions__codename__in=[
                                    'project.view.private']
                                ).values_list('project', flat=True)

        # private archived projects
        ids += prj_roles.filter(project__access='private',
                                project__archived=True,
                                project__extent__isnull=False,
                                group__permissions__codename__in=[
                                    'project.view.private',
                                    'project.view.archived']
                                ).values_list('project', flat=True)
        query = default | Q(id__in=set(ids))
        return all_projects.filter(query)


class OrgRoleCheckMixin(SuperUserCheckMixin, OrganizationMixin):
    """Determin user's organization role and add role membership to context.

       Add `is_member` and `is_admin` context variables and class attributes.
    """

    def get_roles(self):
        if not hasattr(self, '_is_member') or not hasattr(self, '_is_admin'):
            self._is_member = False
            self._is_admin = False

            # Check if the user is anonymous: not an admin
            if isinstance(self.request.user, AnonymousUser):
                return False, False

            # Check if the user is a superuser: is an admin
            if self.is_superuser:
                self._is_member = True
                self._is_admin = True

            if hasattr(self, 'get_organization'):
                org = self.get_organization()
                try:
                    role = OrganizationRole.objects.get(
                        organization=org,
                        user=self.request.user,
                    )
                    self._is_member = True
                    self._is_admin = role.admin
                except OrganizationRole.DoesNotExist:
                    pass

        return self._is_member, self._is_admin

    @property
    def is_administrator(self):
        _, admin = self.get_roles()
        return admin

    @property
    def is_member(self):
        member, _ = self.get_roles()
        return member

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['is_member'] = self.is_member
        context['is_administrator'] = self.is_administrator
        return context

from ckan import model
from ckan.logic import ValidationError, NotFound, get_action
from ckan.lib.helpers import json
from ckan.plugins import toolkit

import logging
log = logging.getLogger(__name__)

from ckanext.harvest.harvesters.ckanharvester import CKANHarvester


class DataVicCKANHarvester(CKANHarvester):
    '''
    A Harvester for CKAN Data.Vic instances
    '''
    config = None

    api_version = 2
    action_api_version = 3

    def info(self):
        return {
            'name': 'datavic_ckan_harvester',
            'title': 'CKAN Data.Vic schema 2',
            'description': 'Harvests remote CKAN instances using the Data.Vic custom schema',
            'form_config_interface': 'Text'
        }

    def import_stage(self, harvest_object):
        log.debug('In CKANHarvester import_stage')

        base_context = {'model': model, 'session': model.Session,
                        'user': self._get_user_name()}
        if not harvest_object:
            log.error('No harvest object received')
            return False

        if harvest_object.content is None:
            self._save_object_error('Empty content for object %s' %
                                    harvest_object.id,
                                    harvest_object, 'Import')
            return False

        self._set_config(harvest_object.job.source.config)

        try:
            package_dict = json.loads(harvest_object.content)

            if package_dict.get('type') == 'harvest':
                log.warn('Remote dataset is a harvest source, ignoring...')
                return True

            # Set default tags if needed
            default_tags = self.config.get('default_tags', [])
            if default_tags:
                if not 'tags' in package_dict:
                    package_dict['tags'] = []
                package_dict['tags'].extend(
                    [t for t in default_tags if t not in package_dict['tags']])

            remote_groups = self.config.get('remote_groups', None)
            if not remote_groups in ('only_local', 'create'):
                # Ignore remote groups
                package_dict.pop('groups', None)
            else:
                if not 'groups' in package_dict:
                    package_dict['groups'] = []

                # check if remote groups exist locally, otherwise remove
                validated_groups = []

                for group_ in package_dict['groups']:
                    try:
                        try:
                            if 'id' in group_:
                                data_dict = {'id': group_['id']}
                                group = get_action('group_show')(base_context.copy(), data_dict)
                            else:
                                raise NotFound

                        except NotFound, e:
                            if 'name' in group_:
                                data_dict = {'id': group_['name']}
                                group = get_action('group_show')(base_context.copy(), data_dict)
                            else:
                                raise NotFound
                        # Found local group
                        validated_groups.append({'id': group['id'], 'name': group['name']})

                    except NotFound, e:
                        log.info('Group %s is not available', group_)
                        if remote_groups == 'create':
                            try:
                                group = self._get_group(harvest_object.source.url, group_)
                            except RemoteResourceError:
                                log.error('Could not get remote group %s', group_)
                                continue

                            for key in ['packages', 'created', 'users', 'groups', 'tags', 'extras', 'display_name']:
                                group.pop(key, None)

                            get_action('group_create')(base_context.copy(), group)
                            log.info('Group %s has been newly created', group_)
                            validated_groups.append({'id': group['id'], 'name': group['name']})

                package_dict['groups'] = validated_groups

            # Local harvest source organization
            source_dataset = get_action('package_show')(base_context.copy(), {'id': harvest_object.source.id})
            local_org = source_dataset.get('owner_org')

            remote_orgs = self.config.get('remote_orgs', None)

            if not remote_orgs in ('only_local', 'create'):
                # Assign dataset to the source organization
                package_dict['owner_org'] = local_org
            else:
                if not 'owner_org' in package_dict:
                    package_dict['owner_org'] = None

                # check if remote org exist locally, otherwise remove
                validated_org = None
                remote_org = package_dict['owner_org']

                if remote_org:
                    try:
                        data_dict = {'id': remote_org}
                        org = get_action('organization_show')(base_context.copy(), data_dict)
                        validated_org = org['id']
                    except NotFound, e:
                        log.info('Organization %s is not available', remote_org)
                        if remote_orgs == 'create':
                            try:
                                try:
                                    org = self._get_organization(harvest_object.source.url, remote_org)
                                except RemoteResourceError:
                                    # fallback if remote CKAN exposes organizations as groups
                                    # this especially targets older versions of CKAN
                                    org = self._get_group(harvest_object.source.url, remote_org)

                                for key in ['packages', 'created', 'users', 'groups', 'tags', 'extras', 'display_name', 'type']:
                                    org.pop(key, None)
                                get_action('organization_create')(base_context.copy(), org)
                                log.info('Organization %s has been newly created', remote_org)
                                validated_org = org['id']
                            except (RemoteResourceError, ValidationError):
                                log.error('Could not get remote org %s', remote_org)

                package_dict['owner_org'] = validated_org or local_org

            # Set default groups if needed
            default_groups = self.config.get('default_groups', [])
            if default_groups:
                if not 'groups' in package_dict:
                    package_dict['groups'] = []
                existing_group_ids = [g['id'] for g in package_dict['groups']]
                package_dict['groups'].extend(
                    [g for g in self.config['default_group_dicts']
                     if g['id'] not in existing_group_ids])

            # Set default extras if needed
            default_extras = self.config.get('default_extras', {})
            def get_extra(key, package_dict):
                for extra in package_dict.get('extras', []):
                    if extra['key'] == key:
                        return extra
            if default_extras:
                override_extras = self.config.get('override_extras', False)
                if not 'extras' in package_dict:
                    package_dict['extras'] = []
                for key, value in default_extras.iteritems():
                    existing_extra = get_extra(key, package_dict)
                    if existing_extra and not override_extras:
                        continue  # no need for the default
                    if existing_extra:
                        package_dict['extras'].remove(existing_extra)
                    # Look for replacement strings
                    if isinstance(value, basestring):
                        value = value.format(
                            harvest_source_id=harvest_object.job.source.id,
                            harvest_source_url=
                            harvest_object.job.source.url.strip('/'),
                            harvest_source_title=
                            harvest_object.job.source.title,
                            harvest_job_id=harvest_object.job.id,
                            harvest_object_id=harvest_object.id,
                            dataset_id=package_dict['id'])

                    package_dict['extras'].append({'key': key, 'value': value})

            for resource in package_dict.get('resources', []):
                # Clear remote url_type for resources (eg datastore, upload) as
                # we are only creating normal resources with links to the
                # remote ones
                resource.pop('url_type', None)

                # Clear revision_id as the revision won't exist on this CKAN
                # and saving it will cause an IntegrityError with the foreign
                # key.
                resource.pop('revision_id', None)

            result = self._create_or_update_package(
                package_dict, harvest_object, package_dict_form='package_show')

            if result:
                new_package = toolkit.get_action('package_show')(base_context.copy(), {'id': package_dict['id']})

                from ckanext.datavicmain.plugins import DatasetForm

                for field in DatasetForm.DATASET_EXTRA_FIELDS:
                    if field[0] in package_dict:
                        new_package[field[0]] = package_dict[field[0]]

                update = toolkit.get_action('package_update')(base_context.copy(), new_package)

            return result

        except ValidationError, e:
            self._save_object_error('Invalid package with GUID %s: %r' %
                                    (harvest_object.guid, e.error_dict),
                                    harvest_object, 'Import')
        except Exception, e:
            self._save_object_error('%s' % e, harvest_object, 'Import')


class ContentFetchError(Exception):
    pass

class ContentNotFoundError(ContentFetchError):
    pass

class RemoteResourceError(Exception):
    pass


class SearchError(Exception):
    pass

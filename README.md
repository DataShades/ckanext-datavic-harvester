# CKAN Datavic Harvester

This is a custom Harvester (https://github.com/ckan/ckanext-harvest) extension for CKAN.

It assumes that the ``ckanext-harvest`` extension is installed and enabled in the CKAN .ini file.

## Installation

To install ``ckanext-datavic-harvester``:

1. Activate your CKAN virtual environment, for example:

        . /usr/lib/ckan/default/bin/activate

2. Install the ckanext-datavic-harvester Python package into your virtual environment:

        cd /usr/lib/ckan/default/src/ckanext-datavic-harvester
        python setup.py develop

3. Add ``datavic_ckan_harvester`` to the ``ckan.plugins`` setting in your CKAN
   config file (by default the config file is located at
   ``/etc/ckan/default/production.ini``).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu:

         sudo service apache2 reload

5. When creating a new harvest source via the standard ``ckanext-harvest`` admin UI, select ``CKAN Data.Vic schema`` as the harvest type.

# snipe-it-api-adapter
API/HTTPPOST adapter layer to snipe-it asset management project to allow semi-automated asset management commands via python while snipe adds a formal API layer, written for 3.5.1

Intended to be used on AWS Lambda, hence not using libraries like BeautifulSoup, etc

#Here are some sample calls that actually work:
	#write out to the asset/monitoring system (variables are defined elsewhere)
	
	from SnipeAPIAdapter import SnipeAPIAdapter
	import json
	import datetime
	from dateutil import parser
	import pytz
	import urllib

	snipe = SnipeAPIAdapter(endpoint, username, password)

	asset_id = snipe.getAssetId(tag=asset_set['category']+"/"+asset_set['serial'])
	if asset_id is not False:
		#does the asset have accurate information?
        	data_asset_edit = snipe.getAssetData(id=asset_id)
        	data_asset_username = snipe.getAssetUsername(tag=asset_set['category']+"/"+asset_set['serial'])

	else:
        	#add a new asset based on our information
        	#defaults
        	monitorable_custom_fields = ["Monitoring"]
        	fieldset_id = snipe.getCustomFieldSets(name="Monitorable", custom_fields=monitorable_custom_fields)
        	status_ids = snipe.getStatusId()
        	deployable_status_id = status_ids['Ready to Deploy']
        	#specifics
        	company_id = snipe.getCompanyId(company)
        	model_id = snipe.getAssetModelId(asset_model_name=asset_set['model'], manufacturer=asset_set['manufacturer'], category=asset_set['category'], custom_fieldset_id=fieldset_id)
        	user_id = snipe.getUserId(username=str(asset_set['vehicle_id']), group=depot)
        	asset_id = snipe.getAssetId(tag=asset_set['category']+"/"+asset_set['serial'], serial=asset_set['serial'], model_id=model_id, company_id=company_id, status_id=deployable_status_id)
        	snipe.checkout(asset_id=asset_id, user_id=user_id)
	
		snipe.cleanup()


#here are some sample calls when I was developing this
        #create custom fieldset with fields if it doesn't exist
        #monitorable_custom_fields = ["Monitoring"]
        #fieldset_id = getCustomFieldSets(name="Monitorable", custom_fields=monitorable_custom_fields)
        #print fieldset_id

        #fieldset_id = 15
        #asset_model_id = getAssetModelId(asset_model_name="test-post-assetmodelD", manufacturer="test-post-ManufacturerF", category="test-post-categoryF", custom_fieldset_id=fieldset_id)
        #print asset_model_id

        #asset_model_id = 8
        #user_id = getUserId("85125", "mjq")
        #asset_id = getAssetId(tag='buscis/384-555-532', model_id=asset_model_id, status_id='6', purchase_date='2016-03-24', custom_field_def={"Monitoring":"test"})

        #asset_id = editAsset(tag='buscis/384-555-532', custom_field_def={"Monitoring":"editedtest"})

        #init stuff if you wish to change things initially
        #if initStatuses():
        #       print("success")

        #run before creating an asset (along with the init stuff)
        #company_id = getCompanyId("test-post-company")
        #manufacturer_id = getManufacturerId("test-post-ManufacturerB")#create this function
        #category_id = getCategoryId("test-post-category")
        #asset_model_id = getAssetModelId(asset_model_name="test-post-assetmodelC", manufacturer="test-post-ManufacturerF", category="test-post-categoryF")
        #supplier_id = getSupplierId(supplier_name="test-post-supplier", contact="test-supplier-contact", phone="6312322235", email="test@gmail.com", notes="test-supplier-notes")
        #location_id = getLocationId(location_name="test-post-depot-location")
        #statuses = getStatusId()

        #user_id = getUserId("85125", "mjq")
        #checkout(asset_id=asset_id, user_id='3')	
	
	# snipe.getCompanyName(2) #retrieves the company name for an id
	#snipe.createMaintenanceAction(asset_id=1, supplier_id=1, maintenancetype="Maintenance", name="autotest", start="2016-12-29")

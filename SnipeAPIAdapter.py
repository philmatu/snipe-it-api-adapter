#!/usr/bin/python

#specific to snipe 3.5.1

import cStringIO
import os
import pycurl
import sys
import tempfile
import json
import string
import random
import time
from HTMLParser import HTMLParser
import urllib

class FieldsetHtmlParser(HTMLParser):
	def __init__(self):
		HTMLParser.__init__(self)
		self.recording = 0
		self.fields = False
		self.fieldsets = {}
		self.temp = None
		self.tempb = None
		self.tempfieldsets = []
		self.ct = 0
	def handle_starttag(self, tag, attributes):
		if self.fields is False: #look at fieldsets first
			if tag == 'a': 
				#look at fields once we find the a tag of the create new field button
				if "/admin/custom_fields/create-field" in str(attributes):
					self.fields = {}
				else:
					for key, value in attributes:
						if key == 'href':
							if "/admin/custom_fields/" in value and "create" not in value:
								t = value.split("/")
								self.temp = t[-1]
		else:
			if tag == 'form':
				if self.ct == 5:
					self.ct = 0
					for key, value in attributes:
						if "/admin/custom_fields/delete-field/" in value:
							t = value.split("/")
							self.fields[t[-1]] = {'name':self.tempb, 'fieldsets':self.tempfieldsets}
							self.tempb = None
							self.tempfieldsets = []
			if tag == 'td':
				self.ct = self.ct + 1
				if self.ct == 1:
					self.temp = True
			if tag == 'a':
				if self.ct == 4:
					for key, value in attributes:
						if "/admin/custom_fields" in value:
							t = value.split("/")
							self.tempfieldsets.append(t[-1])
	def handle_data(self, data):
		if self.temp is not None:
			if self.fields is False:
				self.fieldsets[self.temp] = data
			else:
				self.tempb = data
			self.temp = None
		
	def get_fieldsets(self):
		return self.fieldsets
	
	def get_fields(self):
		return self.fields

class AssetdataHtmlParser(HTMLParser):
	def __init__(self):
		HTMLParser.__init__(self)
		self.recording = 0
		self.data = []
		self.open = False
		self.lastkey = None
		self.lastvalue = None
		self.lastdata = None
		self.lasttag = None
		self.closed = True
		self.lastcheck = False
		self.ischeck = False
	def handle_starttag(self, tag, attributes):
		if tag == 'option':
			if "selected" in str(attributes):
				for key, value in attributes:
					if key == "value":
						self.lastvalue = value
		if tag == 'textarea' or tag == 'select' or tag == 'input':
			self.lastkey = None
			self.lastvalue = None
			self.lastdata = None
			for key, value in attributes:
				if key == "name":
					self.lastkey = value
				if key == "value":
					self.lastvalue = value
				if key == "checked":
					self.lastchecked = True
				if key == "type":
					if value.lower() == "checkbox":
						self.ischeck = True
			#patch for the missing input closing tag on snipeit custom fields parsing
			if self.open and self.lastkey is not None and tag == 'input':
				if self.lastchecked and self.ischeck:
					self.data.append([self.lastkey, "1"])
				else:
					self.data.append([self.lastkey, str(self.lastvalue).strip()])
				self.open = False
				self.lastchecked = False
				self.ischeck = False
				return
			
		if tag == 'textarea':
			self.lasttag = 'textarea'
		self.open = True
			
	def handle_data(self, data):
		if self.open:
			if str(self.lasttag) == 'textarea':
				if self.lastvalue is not None:
					self.lastvalue = self.lastvalue+str(data)
				else:
					self.lastvalue = data
				return
			if not data.startswith("Select") and "No custom fields" not in data:
				self.lastdata = data
	
	def handle_endtag(self, tag):
		if self.lasttag == 'textarea':
			self.lasttag = None
		elif tag == 'select' or tag == 'input' or tag == 'textarea':
			if self.lastdata is not None:
				self.data.append([self.lastkey, str(self.lastvalue).strip(), str(self.lastdata).strip()])
			elif self.lastvalue is not None:
				self.data.append([self.lastkey, str(self.lastvalue).strip()])
			else:
				self.data.append([self.lastkey])
		self.open = False
		self.lastchecked = False
		self.ischeck = False
		
	def getData(self):
		return self.data


class SnipeAPIAdapter():
  #timeout in seconds, endpoint is http://snipeurl.com (no final /)
  def __init__(self, endpoint, username, password, timeout=10):
	self.timeout = timeout
	self.username = username
	self.password = password
	self.endpoint = endpoint
	
	#private variables
	self.glob_token = None
	self.glob_cookie = None

  def cleanup(self):
	self.glob_token = None
	self.glob_cookie = None
	#remove the cookie, we don't need it now (global declaration only needed in sub-functions)
	if self.glob_cookie is not None:
		os.remove(self.glob_cookie.name)#remove the temporary cookie file now that we're done with our login/request

  def curlQuery(self, url_suffix, request_type, post_data=None, header=None):
	if self.glob_cookie is None:
		#set a cookie to login and such
		self.glob_cookie = tempfile.NamedTemporaryFile(delete=False)
		
	response = cStringIO.StringIO()
	c = pycurl.Curl()
	c.setopt(c.URL, str(self.endpoint)+str(url_suffix))
	c.setopt(c.TIMEOUT, self.timeout)
	c.setopt(c.COOKIEJAR, self.glob_cookie.name)
	c.setopt(c.COOKIEFILE, self.glob_cookie.name)
	c.setopt(c.CUSTOMREQUEST, request_type)
	c.setopt(c.WRITEFUNCTION, response.write)
	if header is not None:
		c.setopt(c.HTTPHEADER, header)
	if post_data is not None:
		#e.g. post_data looks like post_data = {'field': 'value'}
		postfields = urllib.urlencode(post_data)
		c.setopt(c.POSTFIELDS, postfields)
	
	running = True
	while running:
		try:
			c.perform()
			running = False
		except:
			print("Failed to query "+str(url_suffix)+"... Retrying")
	
	c.close()
	return response.getvalue()

  def queryAPI(self, api_suffix, post_data_api=None):
	if self.glob_token is None:
		token_response = self.curlQuery(url_suffix="/login", request_type="GET")
		for line in token_response.split("\n"):
			if "_token" in line:
				parts = line.split("\"")
				self.glob_token = parts[5]
				break
		if self.glob_token is None:
			return ""
	
		#actually login
		header = ["Accept: text/html,application/json"]
		post_data = {'_token':self.glob_token,'username':self.username,'password':self.password}
		self.curlQuery(url_suffix="/login", request_type="POST", post_data=post_data, header=header)
	
	#do the api query
	header = ["Accept: text/html,application/json", "_token: "+self.glob_token]
	if post_data_api is None:
		data_reply = self.curlQuery(url_suffix=api_suffix, request_type="GET", header=header)
	else:
		post_data_api.update({'_token':self.glob_token})
		header = ["Accept: text/html,application/json"]
		data_reply = self.curlQuery(url_suffix=api_suffix, request_type="POST", header=header, post_data=post_data_api)
		
	return data_reply

  #returns all of the current status labels and ids for use in asset editing / creation
  def getStatusId(self):
	out = {}
	response = self.queryAPI(api_suffix="/api/statuslabels/list?sort=asc&limit=1000")
	j_resp = json.loads(response)
	if len(j_resp['rows']) > 0:
		for row in j_resp['rows']:
			out[row['name']] = row['id']
	return out
	

  #init to deployed/deployable/54b552, fault/pending/ff0000, spare/deployable/ff7a00, repairing/pending/00cfff
  #in English: deletes all the starting statuses and initiates our statuses (only should be run once at db init, probably)... this is left as lingering code
  def initStatuses(self):
	status = {"Deployed":"Deployable/54b552", "Fault":"Pending/ff0000", "Spare":"Deployable/ff7a00", "Repairing":"Pending/00cfff"}

	#determine if the statuses are already in place, if not, add the new ones and delete the ones already there that shouldn't be there
	unaltered = []
	delete = []
	response = self.queryAPI(api_suffix="/api/statuslabels/list?sort=asc&limit=1000")
	j_resp = json.loads(response)
	for row in j_resp['rows']:
		if row['name'] in status:
			item = status[row['name']]
			parts = item.split("/")
			#row['color'] in format <div class="pull-left" style="margin-right: 5px; height: 20px; width: 20px; background-color: #54b552"></div>#54b552
			if row['type'] in parts[0] and row['color'][-6:] in parts[1]:
				unaltered.append(row['name'])
			else:
				delete.append(row['id'])
		else:
			delete.append(row['id'])
	
	for key,value in status.iteritems():
		if key not in unaltered:
			#add these keys
			parts = value.split("/")
			#status label posted as all lower case...
			post_data = {'name':key, 'statuslabel_types':parts[0].lower(), 'color':"#"+parts[1], 'notes':''}
			response = self.queryAPI(api_suffix="/admin/settings/statuslabels/create", post_data_api=post_data)
			print("added label "+key)
		
	for key in delete:
		url = "/admin/settings/statuslabels/"+key+"/delete"
		response = self.queryAPI(api_suffix=url)
		print("Deleted status "+key)

  def getManufacturerId(self, manufacturer=None):
	if manufacturer is None:
		return False
	reply = self.queryAPI(api_suffix="/api/manufacturers/list?sort=asc&limit=1000&search="+manufacturer)
	j_reply = json.loads(reply)
	for row in j_reply['rows']:
		manu = row['name'].split("\">")[1].split("<")[0]
		if manu == manufacturer:
			return row['id']
	post_data = {'name':manufacturer}
	response = self.queryAPI(api_suffix="/admin/settings/manufacturers/create", post_data_api=post_data)
	return self.getManufacturerId(manufacturer)

  #gets the company name from the ID using the listing page (html parsing)
  def getCompanyName(self, company_id):
	reply = self.queryAPI(api_suffix="/admin/settings/companies")
	start = 0
	id = ""
	for line in reply.split("\n"):
		if start > 0:
			if "<td>" in line:
				if start == 1:
					id = line.split(">")[1].split("<")[0]
				if start == 2:
					name = line.split(">")[1].split("<")[0]
					if str(id).strip() == str(company_id).strip():
						return name
				start = start + 1
			if "</tr>" in line:
				start = 1
		if "Company Name</th>" in line:
			start = 1
	return False

  #creates the company if it doesn't exist
  def getCompanyId(self, company=None):
	if company is None:
		return False
	reply = self.queryAPI(api_suffix="/admin/settings/companies")
	start = 0
	id = ""
	for line in reply.split("\n"):
		if start > 0:
			if "<td>" in line:
				if start == 1:
					id = line.split(">")[1].split("<")[0]
				if start == 2:
					name = line.split(">")[1].split("<")[0]
					if str(name).strip() == str(company).strip():
						return id
				start = start + 1
			if "</tr>" in line:
				start = 1
		if "Company Name</th>" in line:
			start = 1
	#if we make it here, the company doesn't exist
	post_data = {'name':company}
	response = self.queryAPI(api_suffix="/admin/settings/companies/create", post_data_api=post_data)
	return self.getCompanyId(company)

  #defaults to asset type, can also be "accessory", "consumable", or "component"
  def getCategoryId(self, category=None, category_type="asset", eula_text=""):
	if category is None:
		return False
	reply = self.queryAPI(api_suffix="/api/categories/list?sort=asc&limit=1000")
	j_reply = json.loads(reply)
	for row in j_reply['rows']:
		thename = row['name'].split("\">")[1].split("<")[0]
		if thename == category:
			return row['id']
	post_data = {'name':category, 'category_type':category_type, 'eula_text':eula_text}
	response = self.queryAPI(api_suffix="/admin/settings/categories/create", post_data_api=post_data)
	return self.getCategoryId(category)

  def getAssetModelNameFromId(self, asset_id):
	#there shouldn't be more than 1000 asset model names, if there are, this should be rethought out
	reply = self.queryAPI(api_suffix="/api/models/list?sort=asc&limit=1000")
	j_reply = json.loads(reply)
	for row in j_reply['rows']:
		theid = str(row['id'])
		thename = row['name'].split("\">")[1].split("<")[0]
		if str(asset_id) == theid:
			return thename

  #this will automatically create a manufacturer and category if one doesn't exist (as defined here)
  def getAssetModelId(self, asset_model_name=None, manufacturer=None, category=None, model_number="", notes="", custom_fieldset_id=""):
	if asset_model_name is None:
		return False

	reply = self.queryAPI(api_suffix="/api/models/list?sort=asc&limit=1000")
	j_reply = json.loads(reply)
	for row in j_reply['rows']:
		thename = row['name'].split("\">")[1].split("<")[0]
		if thename == asset_model_name:
			return row['id']

	if manufacturer is None or category is None:
		return False
	
	#figure out what the category and manufacturer ids are (or create the missing ones)
	manufacturer_id = self.getManufacturerId(manufacturer)
	
	if str(category).isdigit():
		category_id = category
	else:
		category_id = self.getCategoryId(category)
	
	if category_id is None or manufacturer_id is None:
		return False
	
	post_data = {'name':asset_model_name, 'modelno':model_number, 'note':notes, 'filename':'', 'custom_fieldset':custom_fieldset_id, \
		'eol':'', 'depreciation_id':'', 'category_id':category_id, 'manufacturer_id':manufacturer_id}
	response = self.queryAPI(api_suffix="/hardware/models/create", post_data_api=post_data)
	return self.getAssetModelId(asset_model_name)

  def getSupplierId(self, supplier_name=None, contact="", phone="", email="", notes=""):
	if supplier_name is None:
		return False
	
	reply = self.queryAPI(api_suffix="/api/suppliers/list?sort=asc&limit=1000")
	j_reply = json.loads(reply)
	for row in j_reply['rows']:
		thename = row['name'].split("\">")[1].split("<")[0]
		if thename == supplier_name:
			return row['id']

	post_data = {'name':supplier_name, 'contact':contact, 'phone':phone, 'email':email, 'notes':notes, 'address':'', 'address2':'', 'city':'', 'state':'', 'country':'', 'zip':'', 'fax':'', 'url':''}
	response = self.queryAPI(api_suffix="/admin/settings/suppliers/create", post_data_api=post_data)
	return self.getSupplierId(supplier_name)

  def getLocationName(self, location_id):
	reply = self.queryAPI(api_suffix="/api/locations/list?sort=asc&limit=1000")
	j_reply = json.loads(reply)
	for row in j_reply['rows']:
		thename = row['name'].split("\">")[1].split("<")[0]
		if str(location_id).strip() == str(row['id']).strip():
			return thename
	return False

  def getLocationId(self, location_name=None, address="", city="", state="", zip=""):
	if location_name is None:
		return False
	
	if len(location_name) < 3:
		print("The location "+str(location_name)+" is too short, it must be at least 3 characters")
		return False
	
	reply = self.queryAPI(api_suffix="/api/locations/list?sort=asc&limit=1000")
	j_reply = json.loads(reply)
	for row in j_reply['rows']:
		thename = row['name'].split("\">")[1].split("<")[0]
		if thename == location_name:
			return row['id']

	post_data = {'name':location_name, 'address':address, 'address2':'', 'city':city, 'state':state, 'country':'', 'zip':zip, 'currency':'', 'parent_id':''}
	response = self.queryAPI(api_suffix="/admin/settings/locations/create", post_data_api=post_data)
	return self.getLocationId(location_name)

  def getUserGroupId(self, group_name=None):
	if group_name is None:
		return False
	
	reply = self.queryAPI(api_suffix="/api/groups/list?sort=asc&limit=1000")
	j_reply = json.loads(reply)
	for row in j_reply['rows']:
		if row['name'] == group_name:
			return row['id']

	post_data = {'permission[superuser]':0,'permission[admin]':0,'permission[reports.view]':0,'permission[assets.view]':0, \
		'permission[assets.create]':0, 'permission[assets.edit]':0, 'permission[assets.delete]':0, 'permission[assets.checkin]':0, \
		'permission[assets.checkout]':0, 'permission[assets.view.requestable]':0, 'permission[accessories.view]':0, 'permission[accessories.create]':0, \
		'permission[accessories.edit]':0, 'permission[accessories.delete]':0, 'permission[accessories.checkout]':0, 'permission[accessories.checkin]':0, \
		'permission[consumables.view]':0, 'permission[consumables.create]':0, 'permission[consumables.edit]':0, 'permission[consumables.delete]':0, \
		'permission[consumables.checkout]':0, 'permission[licenses.view]':0, 'permission[licenses.create]':0, 'permission[licenses.edit]':0, \
		'permission[licenses.delete]':0, 'permission[licenses.checkout]':0, 'permission[licenses.keys]':0, 'permission[components.view]':0, \
		'permission[components.create]':0, 'permission[components.edit]':0, 'permission[components.delete]':0, 'permission[components.checkout]':0, \
		'permission[components.checkin]':0, 'permission[users.view]':0, 'permission[users.create]':0, 'permission[users.edit]':0, 'permission[users.delete]':0, \
		'name':group_name}
	response = self.queryAPI(api_suffix="/admin/groups/create", post_data_api=post_data)
	return self.getUserGroupId(group_name)

  #gets all the users in the system (100k of them at least... if we have more than this, there is likely an issue)
  def getUserIds(self, prefix=""):
	#need to loop for this data (1000 max at a time supported by snipe)
	offset = 0
	total = 1
	ids = {}
	
	#doing 1000 at a time
	while offset < total:
		print ("User ids retrieving query offset "+str(offset)+" of total user count "+str(total))
		response = self.queryAPI(api_suffix="/api/users/list?sort=asc&offset="+str(offset)+"&limit=1000&search="+prefix)
		j_response = json.loads(response)
		total = j_response['total']
		offset = offset + 1000
		for row in j_response['rows']:
			ids.update({row['id']:row['username']})
	return ids
	 
  #changes the group of the user id in 3 queries (we shouldn't use this often enough to justify using a cached group name)
  def editUserGroup(self, username, group):
	user_id = False
	request = self.queryAPI(api_suffix="/api/users/list?sort=asc&limit=25&search="+username)
	j_request = json.loads(request)
	for item in j_request['rows']:
		if item['username'] == username:
			user_id = item['id']
	new_group_id = self.getUserGroupId(group_name=group)
	if new_group_id is False or user_id is False:
		return False
		
	post_data = {'permission[superuser]':0,'permission[admin]':0,'permission[reports.view]':0,'permission[assets.view]':0, \
		'permission[assets.create]':0, 'permission[assets.edit]':0, 'permission[assets.delete]':0, 'permission[assets.checkin]':0, \
		'permission[assets.checkout]':0, 'permission[assets.view.requestable]':0, 'permission[accessories.view]':0, 'permission[accessories.create]':0, \
		'permission[accessories.edit]':0, 'permission[accessories.delete]':0, 'permission[accessories.checkout]':0, 'permission[accessories.checkin]':0, \
		'permission[consumables.view]':0, 'permission[consumables.create]':0, 'permission[consumables.edit]':0, 'permission[consumables.delete]':0, \
		'permission[consumables.checkout]':0, 'permission[licenses.view]':0, 'permission[licenses.create]':0, 'permission[licenses.edit]':0, \
		'permission[licenses.delete]':0, 'permission[licenses.checkout]':0, 'permission[licenses.keys]':0, 'permission[components.view]':0, \
		'permission[components.create]':0, 'permission[components.edit]':0, 'permission[components.delete]':0, 'permission[components.checkout]':0, \
		'permission[components.checkin]':0, 'permission[users.view]':0, 'permission[users.create]':0, 'permission[users.edit]':0, 'permission[users.delete]':0, \
		'first_name':username, 'last_name':'', 'username':username, 'password':'', 'password_confirm':'', 'email':'', 'company_id':0, 'locale':'', \
		'employee_num':'', 'jobtitle':'', 'manager_id':'', 'location_id':'', 'phone':'', 'activated':1, 'notes':'', 'groups[]':new_group_id}
	response = self.queryAPI(api_suffix="/admin/users/"+str(user_id)+"/edit", post_data_api=post_data)
	return True

  #creates a user and returns that ID if nothing found
  #bus is the default group for new vehicles that hold hardware (users are containers here)
  def getUserId(self, username=None, group="bus"):
	if username is None:
		return False
	
	request = self.queryAPI(api_suffix="/api/users/list?sort=asc&limit=1000&search="+username)
	j_request = json.loads(request)
	for item in j_request['rows']:
		if item['username'] == username:
			return item['id']
	
	group_id = self.getUserGroupId(group_name=group)

	#create the user
	random_pass = ''.join(random.sample(string.ascii_uppercase + string.digits*8, 8))
	post_data = {'permission[superuser]':0,'permission[admin]':0,'permission[reports.view]':0,'permission[assets.view]':0, \
		'permission[assets.create]':0, 'permission[assets.edit]':0, 'permission[assets.delete]':0, 'permission[assets.checkin]':0, \
		'permission[assets.checkout]':0, 'permission[assets.view.requestable]':0, 'permission[accessories.view]':0, 'permission[accessories.create]':0, \
		'permission[accessories.edit]':0, 'permission[accessories.delete]':0, 'permission[accessories.checkout]':0, 'permission[accessories.checkin]':0, \
		'permission[consumables.view]':0, 'permission[consumables.create]':0, 'permission[consumables.edit]':0, 'permission[consumables.delete]':0, \
		'permission[consumables.checkout]':0, 'permission[licenses.view]':0, 'permission[licenses.create]':0, 'permission[licenses.edit]':0, \
		'permission[licenses.delete]':0, 'permission[licenses.checkout]':0, 'permission[licenses.keys]':0, 'permission[components.view]':0, \
		'permission[components.create]':0, 'permission[components.edit]':0, 'permission[components.delete]':0, 'permission[components.checkout]':0, \
		'permission[components.checkin]':0, 'permission[users.view]':0, 'permission[users.create]':0, 'permission[users.edit]':0, 'permission[users.delete]':0, \
		'first_name':username, 'last_name':'', 'username':username, 'password':random_pass, 'password_confirm':random_pass, 'email':'', 'company_id':0, 'locale':'', \
		'employee_num':'', 'jobtitle':'', 'manager_id':'', 'location_id':'', 'phone':'', 'activated':1, 'notes':'', 'groups[]':group_id}
	response = self.queryAPI(api_suffix="/admin/users/create", post_data_api=post_data)
	return self.getUserId(username) #simply call this function again to get the user id once we've posted.

  #gets all the assets in the system (250k of them at least... if we have more than this, there is likely an issue)
  def getAssetIds(self, prefix=""):
	ids = {}
	#need to loop for this data (1000 max at a time supported by snipe)
	offset = 0
	total = 1
	
	#doing 1000 at a time
	while offset < total:
		print ("Asset ids retrieving query offset "+str(offset)+" of total asset count "+str(total))
		response = self.queryAPI(api_suffix="/api/hardware/list?sort=asc&limit=1000&offset="+str(offset)+"&search="+prefix)
		j_response = json.loads(response)
		total = j_response['total']
		offset = offset + 1000
		for row in j_response['rows']:
			thename = row['name'].split("\">")[1].split("<")[0].replace("\\", "")
			theid = row['id']
			ids.update({theid:thename})
	return ids

  def getAssetId(self, tag=None, user_id="", model_id=None, status_id=None, serial="", company_id="", supplier_id="", purchase_date="", purchase_cost="", order="", warranty_months="", notes="", location_id="", custom_field_def={}):
	if tag is None:
		return False
	if purchase_cost is not "":
		purchase_cost = ("%.2f" % float(purchase_cost))
	
	response = self.queryAPI(api_suffix="/api/hardware/list?sort=asc&limit=25&search="+tag)
	j_response = json.loads(response)
	for row in j_response['rows']:
		thename = row['name'].split("\">")[1].split("<")[0].replace("\\", "")
		if thename == tag:
			return row['id']
	
	if model_id is None or status_id is None:
		return False #return false for these only if we aren't doing a lookup

	#purchase_date in yyyy-mm-dd
	post_data = {'asset_tag':tag, 'model_id':model_id, 'status_id':status_id, 'assigned_to':user_id, 'serial':serial, 'name':tag, 'company_id':company_id, \
		'purchase_date':purchase_date, 'supplier_id':supplier_id, 'order_number':order, 'purchase_cost':purchase_cost, 'warranty_months':warranty_months, \
		'notes':notes, 'rtd_location_id':location_id, 'requestable':0, 'image':''}
	if len(custom_field_def) > 0:
		for key in custom_field_def:
			thekey = "_snipeit_"+key.lower()
			post_data[thekey] = custom_field_def[key]
	response = self.queryAPI(api_suffix="/hardware/create", post_data_api=post_data)
	return self.getAssetId(tag)

  def getAssetUsername(self, tag=None):
	if not id:
		return False
	response = self.queryAPI(api_suffix="/api/hardware/list?search="+str(tag))
	j_response = json.loads(response)
	for row in j_response['rows']:
		thename = row['name'].split("\">")[1].split("<")[0].replace("\\", "")
		if thename == tag:
			return row['assigned_to'].split("\">")[1].split("<")[0].replace("\\", "")
	return False

  def getAllUsersMap(self, prefix):
	#get all of the current users in snipe (for vehicle users)
	currentusers_byid = self.getUserIds(prefix=prefix)
	currentusers = {}
	for key in currentusers_byid:
		tid = str(key)
		tuser = str(currentusers_byid[key]).lower()
		if tuser in currentusers:
			print("WARN: the user "+tuser+" is already in the current users cache with id "+str(currentusers[tuser])+", it will be replaced with id "+str(tid))
		currentusers.update({tuser:tid})
	return currentusers

  #example method call: 
  #grabs all of the asset data, similarly to getAssetData with all users/ids, but a full array, memory intensive
  def getAllAssetDataForEditing(self, prefix="", custom_field_def=[]):
	data = {}#assetid:data
	#need to loop for this data (1000 max at a time supported by snipe)
	offset = 0
	total = 1

	#get the status ids in the system
	status_ids = self.getStatusId()
	
	company_ids = {} #in format "agency":"id"
	
	#doing 1000 at a time
	while offset < total:
		print ("Asset ids retrieving query offset "+str(offset)+" of total asset count "+str(total))
		response = self.queryAPI(api_suffix="/api/hardware/list?sort=asc&limit=1000&offset="+str(offset)+"&search="+prefix)
		j_response = json.loads(response)
		total = j_response['total']
		offset = offset + 1000
		for row in j_response['rows']:
			#supplier is not supported by the api to allow bulk editing, this should only change once on create anyways (or modified manually in bulk)
			#warranty is not supported by the api to allow bulk editing, this shoudl only change once on create anyways (or modified manually in bulk)
			#requestable is not supported by the api, so this is also ommitted
			
			post_data = {'asset_tag':'', 'model_id':'', 'assigned_to':'', 'serial':'', 'name':'', 'company_id':'', \
				'purchase_date':'', 'order_number':'', 'purchase_cost':'', 'notes':'', 'rtd_location_id':'', 'image':''}
	
			if len(custom_field_def) > 0:
				for key in custom_field_def:
					thekey = "_snipeit_"+key.lower()
					post_data[thekey] = ''
			if len(str(row['asset_tag']).strip()) > 0:

				#status_id is only updated if it's not "deployed"
				if str(row['status_label']).strip().lower() != "deployed":
					if str(row['status_label']).strip() in status_ids:
						post_data.update({'status_id':str(status_ids[str(row['status_label']).strip()]).strip()})
				
				post_data['asset_tag'] = str(row['asset_tag']).split("\">")[1].split("<")[0].replace("\\", "")
				post_data['model_id'] = str(row['model']).split("/hardware/models/")[1].split("/view\"")[0]
				post_data['assigned_to'] = str(row['assigned_to']).split("admin/users/")[1].split("/view\"")[0]
				post_data['serial'] = str(row['serial']).strip()
				post_data['name'] = str(row['name']).split("\">")[1].split("<")[0].replace("\\", "")
				
				if str(row['companyName']).strip() not in company_ids:
					print("query companyid for "+str(row['companyName']).strip())
					company_id = self.getCompanyId(str(row['companyName']).strip()) #returns a company id or creates one
					company_ids.update({str(row['companyName']).strip():str(company_id)})
				
				post_data['company_id'] = company_ids[str(row['companyName']).strip()]
				if str(row['purchase_date']).strip().lower() != "none":
					post_data['purchase_date'] = str(row['purchase_date']).strip()
				post_data['order_number'] = str(row['order_number']).strip()
				if str(row['purchase_cost']).strip().lower() != "none":
					post_data['purchase_cost'] = str(row['purchase_cost']).strip()
				post_data['notes'] = str(row['notes']).strip()
				post_data['rtd_location_id'] = str(row['location']).split("settings/locations/")[1].split("/view\"")[0]
				
				if len(str(row['image']).strip()) > 0:
					post_data['image'] = str(row['image']).strip()
				
				#handle custom fields
				if len(custom_field_def) > 0:
					for key in custom_field_def:
						thekey = "_snipeit_"+key.lower()
						post_data[thekey] = str(row[thekey]).strip()
				theid = str(row['id']).strip()
				data.update({theid:post_data})
	return data

  def getAssetData(self, id=None, custom_field_def=[]):
	if not id:
		return False
	if not str(id).isdigit():
		return False

	#get the data from the edit page by parsing the HTML form fields
	html = self.queryAPI(api_suffix="/hardware/"+str(id)+"/edit")
	parser = AssetdataHtmlParser()
	parser.feed(html)
	data = parser.getData()
	parser.close()
	
	post_data = {'asset_tag':'', 'model_id':'', 'status_id':'', 'assigned_to':'', 'serial':'', 'name':'', 'company_id':'', \
		'purchase_date':'', 'supplier_id':'', 'order_number':'', 'purchase_cost':'', 'warranty_months':'', \
		'notes':'', 'rtd_location_id':'', 'requestable':'', 'image':''}
	
	if len(custom_field_def) > 0:
		for key in custom_field_def:
			thekey = "_snipeit_"+key.lower()
			post_data[thekey] = ''
	
	for item in data:
		if item[0] in post_data:
			if len(item) > 1:
				if len(item[1]) > 0:
					if not item[1].lower().strip() == "none":
						post_data[item[0]] = item[1]
	return post_data

  def editAsset(self, tag=None, data_array=None, asset_id=None, model_id=None, status_id=None, serial=None, company_id=None, supplier_id=None, purchase_date=None, purchase_cost=None, order=None, warranty_months=None, notes=None, location_id=None, custom_field_def={}):
	if tag is None:
		#to do the data array post (editing from outside source), we must have both the asset id and data array with ALL variables populated correctly
		if data_array is None or asset_id is None:
			return False
		#use the data array to post back to the management system
		self.queryAPI(api_suffix="/hardware/"+str(asset_id)+"/edit", post_data_api=data_array)
		return True
	
	if purchase_cost is not None:
		purchase_cost = ("%.2f" % float(purchase_cost))
	asset_id = self.getAssetId(tag)
	if not asset_id:
		return False
	existing_data = self.getAssetData(id=asset_id, custom_field_def=custom_field_def)
	
	#purchase_date in yyyy-mm-dd
	edit_data = {'asset_tag':tag, 'model_id':model_id, 'status_id':status_id, 'serial':serial, 'name':tag, 'company_id':company_id, \
		'purchase_date':purchase_date, 'supplier_id':supplier_id, 'order_number':order, 'purchase_cost':purchase_cost, 'warranty_months':warranty_months, \
		'notes':notes, 'rtd_location_id':location_id, 'requestable':'', 'image':''}
	
	if len(custom_field_def) > 0:
		for key in custom_field_def:
			thekey = "_snipeit_"+key.lower()
			edit_data[thekey] = custom_field_def[key]
	
	changes = []
	for key in edit_data:
		value = edit_data[key]
		if value is not None:
			if str(existing_data[key]) == str(edit_data[key]):
				continue
			changes.append([key, str(existing_data[key]), str(edit_data[key])])
			existing_data[key] = edit_data[key]

	if len(changes) > 0:
		existing_data['notes'] = "ChangesTimeKeyOldNew("+time.strftime("%Y-%m-%d %H:%M:%S")+"): "+str(changes)+"\n"+existing_data['notes']

		#publish the data with a new note
		self.queryAPI(api_suffix="/hardware/"+str(asset_id)+"/edit", post_data_api=existing_data)
		print "Data Edited Successfully on asset "+str(tag)+"("+str(asset_id)+")! Changes(keyoldnew): "+str(changes)
	return asset_id

  #checkout_date in yyyy-mm-dd
  def checkout(self, asset_id=None, user_id=None, checkout_date=None, notes=''):
	if asset_id is None or user_id is None:
		return False
	if checkout_date is None:
		checkout_date = time.strftime("%Y-%m-%d")
	if not str(asset_id).isdigit() or not str(user_id).isdigit():
		return False

	post_data = {'assigned_to':user_id, 'checkout_at':checkout_date, 'expected_checkin':'', 'note':notes}
	response = self.queryAPI(api_suffix="/hardware/"+str(asset_id)+"/checkout", post_data_api=post_data)
	return True

  #create a new maintenance action, maintenacetype is "Repair", "Upgrade", "Maintenance"; start/end are in yyyy-mm-dd; one of supplier_name or supplier_id must be filled in
  def createMaintenanceAction(self, asset_id, maintenancetype, name, start, supplier_id="", supplier_name="", end="", warrantyImprovement=False, cost="", notes=""):
	types = ["Repair", "Upgrade", "Maintenance"]
	if not str(asset_id).isdigit() or maintenancetype not in types or len(name) < 4:
		return False
	
	if len(str(supplier_id)) < 1:
		if len(supplier_name) < 4:
			return False
		supplier_id = self.getSupplierId(supplier_name=supplier_name)
	
	post_data = {'asset_id':asset_id, 'supplier_id':supplier_id, 'asset_maintenance_type':maintenancetype, 'title':name, 'start_date':start, \
		'completion_date':end, 'cost':cost, 'notes':notes}
	
	if warrantyImprovement is True:
		post_data.update({'is_warranty':1})
	
	response = self.queryAPI(api_suffix="/admin/asset_maintenances/create", post_data_api=post_data)
	return True

  def getCustomFieldData(self):
	#get the data from the edit page by parsing the HTML form fields	
	html = self.queryAPI(api_suffix="/admin/custom_fields")
        parser = FieldsetHtmlParser()
        parser.feed(html)
	fieldsets = parser.get_fieldsets()
	fields = parser.get_fields()
        parser.close()
	return [fieldsets, fields]

  #only add fieldsets that don't exist
  def getCustomFieldSets(self, name=None, custom_fields=[]):
	if name is None:
		return False

	[fieldsets, fields] = self.getCustomFieldData()
	
	fieldset_id = None
	for key in fieldsets:
		if fieldsets[key] == name:
			fieldset_id = key
	
	#we submitted only a name to get the id
	if len(custom_fields) < 1:
		if fieldset_id is not None:
			return fieldset_id
	elif fieldset_id is not None: #we submitted a name and fields... let's verify our picture is what exists
		matches = []
		for key in fields:
			if str(fieldset_id) in fields[key]['fieldsets']:
				matches.append(fieldsets[str(fieldset_id)])
		#match found
		if len(custom_fields) == len(matches):
			return fieldset_id
		#no match found
		else:
			return False
	else:
		#let's add this fieldset / fields
		new_fields = []
		existing_fields = []
		for key in fields:
			existing_fields.append(fields[key]['name'])
		for customfield in custom_fields:
			if customfield not in existing_fields:
				new_fields.append(customfield)
		
		#add new fields 
		if len(new_fields) > 0:
			for thefn in new_fields:
				post_data = {'name':thefn, 'element':'text', 'field_values':'', 'format':'ANY', 'custom_format':''}
				self.queryAPI(api_suffix="/admin/custom_fields/create-field", post_data_api=post_data)
		
		#add the fieldset
		[fieldsets, fields] = self.getCustomFieldData()
		assoc_fids = []
		for key in fields:
			if fields[key]['name'] in custom_fields:
				assoc_fids.append(key)
		order = 0
		post_data = {'name':name}
		result = self.queryAPI(api_suffix="/admin/custom_fields", post_data_api=post_data)
		for line in result.split("\n"):
			if "http-equiv=\"refresh\"" in line:
				new_fs_id = line.split("\"")[-2].split("/")[-1]
				for fkey in assoc_fids:
					order = order + 1
					post_data = {'order':str(order), 'field_id':str(fkey)}
					self.queryAPI(api_suffix="/admin/custom_fields/"+str(new_fs_id)+"/associate", post_data_api=post_data)
				return new_fs_id
	return False

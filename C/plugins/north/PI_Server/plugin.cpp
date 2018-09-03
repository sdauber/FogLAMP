/*
 * FogLAMP PI_Server north plugin.
 *
 * Copyright (c) 2018 Dianomic Systems
 *
 * Released under the Apache 2.0 Licence
 *
 * Author: Massimiliano Pinto
 */
#include <plugin_api.h>
#include <stdio.h>
#include <stdlib.h>
#include <strings.h>
#include <string>
#include <logger.h>
#include <plugin_exception.h>
#include <iostream>
#include <omf.h>
#include "simple_http.h"
#include <simple_https.h>
#include <config_category.h>

using namespace std;

#define PLUGIN_NAME "PI_Server"

/**
 * Plugin specific default configuration
 */
#define PLUGIN_DEFAULT_CONFIG "{ " \
			"\"plugin\": { " \
				"\"description\": \"PI Server North C Plugin\", " \
				"\"type\": \"string\", " \
				"\"default\": \"" PLUGIN_NAME "\" }, " \
			"\"URL\": { " \
				"\"description\": \"The URL of the PI Connector to send data to\", " \
				"\"type\": \"string\", " \
				"\"default\": \"https://pi-server:5460/ingress/messages\" }, " \
			"\"producerToken\": { " \
				"\"description\": \"The producer token that represents this FogLAMP stream\", " \
				"\"type\": \"string\", \"default\": \"omf_north_0001\" }, " \
			"\"OMFHttpTimeout\": { " \
				"\"description\": \"Timeout in seconds for the HTTP operations with the OMF PI Connector Relay\", " \
				"\"type\": \"integer\", \"default\": \"10\" }, " \
			"\"OMFMaxRetry\": { " \
				"\"description\": \"Max number of retries for the communication with the OMF PI Connector Relay\", " \
				"\"type\": \"integer\", \"default\": \"3\" }, " \
			"\"OMFRetrySleepTime\": { " \
        			"\"description\": \"Seconds between each retry for the communication with the OMF PI Connector Relay, " \
                       		"NOTE : the time is doubled at each attempt.\", \"type\": \"integer\", \"default\": \"1\" }, " \
			"\"StaticData\": { " \
				"\"description\": \"Static data to include in each sensor reading sent to PI Server.\", " \
				"\"type\": \"string\", \"default\": \"Location: Palo Alto, Company: Dianomic\" }, " \
			"\"formatNumber\": { " \
        			"\"description\": \"OMF format property to apply to the type Number\", " \
				"\"type\": \"string\", \"default\": \"float64\" }, " \
			"\"formatInteger\": { " \
        			"\"description\": \"OMF format property to apply to the type Integer\", " \
				"\"type\": \"string\", \"default\": \"int64\" } " \
		" }"

/**
 * The PI Server plugin interface
 */
extern "C" {

/**
 * The C API plugin information structure
 */
static PLUGIN_INFORMATION info = {
	PLUGIN_NAME,			// Name
	"1.1.0",			// Version
	0,				// Flags
	PLUGIN_TYPE_NORTH,		// Type
	"1.0.0",			// Interface version
	PLUGIN_DEFAULT_CONFIG		// Configuration
};

/**
 * All categories listed here are fetched via
 * "plugin_extra_config" API method
 *
 * The code wich loads this plugin must
 * create/update these categories and pass back
 * to the plugin via "plugin_init" the additional
 * category items in this form: CATEGORY.ITEM_NAME
 *
 * Example: once OMF_TYPES has been fetched
 * by the code which loads this plugin,
 * the OMF_TYPES.type-id item is passed
 * as an additional item
 */
static const string additional_config_categories =
			"{"
			    "\"OMF_TYPES\": {"
				"\"type-id\": { "
				    "\"description\": \"Identify sensor and measurement types\", "
				    "\"type\": \"integer\", "
				    "\"default\": \"0001\" }"
			    "}"
			"}";

/**
 * Historian PI Server connector info
 */
typedef struct
{
	HttpSender	*sender;  // HTTP/HTTPS connection
	OMF 		*omf;     // OMF data protocol
} CONNECTOR_INFO;

/**
 * Return the information about this plugin
 */
PLUGIN_INFORMATION *plugin_info()
{
	return &info;
}

/**
 * Return default plugin configuration:
 * plugin specific and types_id
 */
const string& plugin_extra_config()
{
	return additional_config_categories;
}

/**
 * Initialise the plugin with configuration.
 *
 * This function is called to get the plugin handle.
 */
PLUGIN_HANDLE plugin_init(ConfigCategory* configData)
{
	/**
	 * Handle PI Server parameters here
	 */
	string url = configData->getValue("URL");
	unsigned int timeout = atoi(configData->getValue("OMFHttpTimeout").c_str());
	string producerToken = configData->getValue("producerToken");

	string formatNumber = configData->getValue("formatNumber");
	string formatInteger = configData->getValue("formatInteger");

	/**
	 * Handle extra config parameters here (i.e. OMF_TYPES)
	 */
	if (!configData->itemExists("OMF_TYPES.type-id"))
	{
		Logger::getLogger()->error("%s: needed 'type-id' item from "
					   "extra category 'OMF_TYPES' not found. "
					   "Be sure all additional category items are "
					   "passed to 'plugin_info'. "
					   "Initialisation failed.",
					   PLUGIN_NAME);
		return NULL;
	}

	string typesId = configData->getValue("OMF_TYPES.type-id");

	/**
	 * Extract host, port, path from URL
	 */
	size_t findProtocol = url.find_first_of(":");
	string protocol = url.substr(0,findProtocol);

	string tmpUrl = url.substr(findProtocol + 3);
	size_t findPort = tmpUrl.find_first_of(":");
	string hostName = tmpUrl.substr(0, findPort);

	size_t findPath = tmpUrl.find_first_of("/");
	string port = tmpUrl.substr(findPort + 1 , findPath - findPort -1);
	string path = tmpUrl.substr(findPath);

	string hostAndPort(hostName + ":" + port);

	CONNECTOR_INFO *connectorInfo = new CONNECTOR_INFO;
	/**
	 * Allocate the HTTPS handler for "Hostname : port"
	 * connect_timeout and request_timeout.
	 * Default is no timeout at all
	 */
	if (protocol == string("http"))
	{
		connectorInfo->sender = new SimpleHttp(hostAndPort,
							timeout,
							timeout);
	}
	else if (protocol == string("https"))
	{
		connectorInfo->sender = new SimpleHttps(hostAndPort,
							timeout,
							timeout);
	}
	else
	{
		Logger::getLogger()->error("Didn't find http/https prefix "
					   "in URL='%s', cannot proceed",
					   url.c_str());
		return NULL;
	}

	// Allocate the PI Server data protocol
	connectorInfo->omf = new OMF(*connectorInfo->sender,
				     path,
				     typesId,
				     producerToken);

	connectorInfo->omf->setFormatType(OMF_TYPE_FLOAT, formatNumber);
	connectorInfo->omf->setFormatType(OMF_TYPE_INTEGER, formatInteger);

	Logger::getLogger()->info("%s plugin configured: URL=%s, "
				  "producerToken=%s, OMF_types_id=%s",
				  PLUGIN_NAME,
				  url.c_str(),
				  producerToken.c_str(),
				  typesId.c_str());


	// Return plugin handle
	return (PLUGIN_HANDLE)connectorInfo;
}

/**
 * Send Readings data to historian server
 */
uint32_t plugin_send(const PLUGIN_HANDLE handle,
		     const vector<Reading *>& readings)
{
	CONNECTOR_INFO *connInfo = (CONNECTOR_INFO *)handle;
	return connInfo->omf->sendToServer(readings);
}

/**
 * Shutdown the plugin
 *
 * Delete allocated data
 *
 * @param handle    The plugin handle
 */
void plugin_shutdown(PLUGIN_HANDLE handle)
{
	CONNECTOR_INFO *connInfo = (CONNECTOR_INFO *)handle;

	// Delete connector data
	delete connInfo->sender;
	delete connInfo->omf;

	// Delete the handle
	delete connInfo;

}

// End of extern "C"
};

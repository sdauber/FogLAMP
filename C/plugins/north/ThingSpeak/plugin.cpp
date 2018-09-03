/*
 * FogLAMP ThingSpeak north plugin.
 *
 * Copyright (c) 2018 Dianomic Systems
 *
 * Released under the Apache 2.0 Licence
 *
 * Author: Mark Riddoch, Massimiliano Pinto
 */
#include <plugin_api.h>
#include <stdio.h>
#include <stdlib.h>
#include <strings.h>
#include <string>
#include <logger.h>
#include <plugin_exception.h>
#include <iostream>
#include <thingspeak.h>
#include <simple_https.h>
#include <config_category.h>
#include <storage_client.h>
#include <rapidjson/document.h>

using namespace std;
using namespace rapidjson;

/**
 * Plugin specific default configuration
 */
#define PLUGIN_DEFAULT_CONFIG "{ " \
			"\"plugin\": { " \
				"\"description\": \"ThingSpeak North\", " \
				"\"type\": \"string\", " \
				"\"default\": \"thingspeak\" }, " \
			"\"URL\": { " \
				"\"description\": \"The URL of the ThingSpeak service\", " \
				"\"type\": \"string\", " \
				"\"default\": \"https://api.thingspeak.com/channels\" }, " \
			"\"channelId\": { " \
				"\"description\": \"The channel id for this thingSpeak channel\", " \
				"\"type\": \"string\", \"default\": \"0\" }, " \
			"\"write_api_key\": { " \
				"\"description\": \"The write_api_key supplied by ThingSpeak for this channel\", " \
				"\"type\": \"string\", \"default\": \"\" }, " \
			"\"fields\": { " \
				"\"description\": \"The fields to send ThingSpeak\", " \
				"\"type\": \"JSON\", \"default\": { " \
				    "\"elements\":[" \
				    "{ \"asset\":\"sinusoid\"," \
				    "\"reading\":\"sinusoid\"}" \
				"]} } " \
		"}"

/**
 * The ThingSpeak plugin interface
 */
extern "C" {

/**
 * The C API plugin information structure
 */
static PLUGIN_INFORMATION info = {
	"ThingSpeak",			// Name
	"1.0.0",			// Version
	0,				// Flags
	PLUGIN_TYPE_NORTH,		// Type
	"1.0.0",			// Interface version
	PLUGIN_DEFAULT_CONFIG		// Configuration
};

/**
 * Return the information about this plugin
 */
PLUGIN_INFORMATION *plugin_info()
{
	return &info;
}

/**
 * Initialise the plugin with configuration.
 *
 * This funcion is called to get the plugin handle.
 */
PLUGIN_HANDLE plugin_init(const ConfigCategory* configData)
{
	if (!configData->itemExists("URL"))
	{
		Logger::getLogger()->fatal("ThingSpeak plugin must have a URL defined for the ThinkSpeak API");
		throw exception();
	}
	string url = configData->getValue("URL");
	if (!configData->itemExists("channelId"))
	{
		Logger::getLogger()->fatal("ThingSpeak plugin must have a channel ID defined");
		throw exception();
	}
	int channel = atoi(configData->getValue("channelId").c_str());
	if (!configData->itemExists("fields"))
	{
		Logger::getLogger()->fatal("ThingSpeak plugin must have a field list defined");
		throw exception();
	}
	string apiKey = configData->getValue("write_api_key");

	ThingSpeak *thingSpeak = new ThingSpeak(url, channel, apiKey);
	thingSpeak->connect();

	if (!configData->itemExists("fields"))
	{
		Logger::getLogger()->fatal("ThingSpeak plugin must have a field list defined");
		throw exception();
	}
	string fields = configData->getValue("fields");
	Document doc;
	doc.Parse(fields.c_str());
	if (!doc.HasParseError())
	{
		if (!doc.HasMember("elements"))
		{
			Logger::getLogger()->fatal("ThingSpeak plugin fields JSON document is missing \"elements\" property");
			throw exception();
		}
		for (Value::ConstValueIterator itr = doc["elements"].Begin();
                                                itr != doc["elements"].End(); ++itr)
		{
			thingSpeak->addField((*itr)["asset"].GetString(),(*itr)["reading"].GetString());
		}
	}
	else
	{
		Logger::getLogger()->fatal("ThingSpeak plugin fields JSON document is badly formed");
		throw exception();
	}

	Logger::getLogger()->info("ThingSpeak plugin configured: URL=%s, "
				  "apiKey=%s, ChannelId=%d",
				  url.c_str(),
				  apiKey.c_str(),
				  channel);

	return (PLUGIN_HANDLE)thingSpeak;
}

/**
 * Send Readings data to historian server
 */
uint32_t plugin_send(const PLUGIN_HANDLE handle,
		     const vector<Reading *>& readings)
{
ThingSpeak	*thingSpeak = (ThingSpeak *)handle;

	return thingSpeak->send(readings);
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
ThingSpeak	*thingSpeak = (ThingSpeak *)handle;

        delete thingSpeak;
}

// End of extern "C"
};

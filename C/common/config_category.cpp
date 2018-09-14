/*
 * FogLAMP category management
 *
 * Copyright (c) 2018 Dianomic Systems
 *
 * Released under the Apache 2.0 Licence
 *
 * Author: Mark Riddoch, Massimiliano Pinto
 */
#include <config_category.h>
#include <string>
#include <rapidjson/document.h>
#include <rapidjson/ostreamwrapper.h>
#include <rapidjson/writer.h>
#include "rapidjson/error/error.h"
#include "rapidjson/error/en.h"
#include <sstream>
#include <iostream>
#include <time.h>
#include <stdlib.h>
#include <logger.h>

using namespace std;
using namespace rapidjson;

/**
 * ConfigCategories constructor without parameters
 *
 * Elements can be added with ConfigCategories::addCategoryDescription
 */
ConfigCategories::ConfigCategories()
{
}

/**
 * Construct a ConfigCategories object from a JSON document returned from
 * the FogLAMP configuratrion service.
 */
ConfigCategories::ConfigCategories(const std::string& json)
{
	Document doc;
	doc.Parse(json.c_str());
	if (doc.HasParseError())
	{
		Logger::getLogger()->error("Configuration parse error in %s: %s at %d", json.c_str(),
			GetParseError_En(doc.GetParseError()), (unsigned)doc.GetErrorOffset());
		throw new ConfigMalformed();
	}
	if (doc.HasMember("categories"))
	{
		const Value& categories = doc["categories"];
		if (categories.IsArray())
		{
			// Process every rows and create the result set
			for (auto& cat : categories.GetArray())
			{
				if (!cat.IsObject())
				{
					throw new ConfigMalformed();
				}
				ConfigCategoryDescription *value = new ConfigCategoryDescription(cat["key"].GetString(),
							cat["description"].GetString());
				m_categories.push_back(value);
			}
		}
		else
		{
			throw new ConfigMalformed();
		}
	}
}

/**
 * ConfigCategories destructor
 */
ConfigCategories::~ConfigCategories()
{
	for (auto it = m_categories.cbegin(); it != m_categories.cend(); it++)
	{
		delete *it;
	}
}

/**
 * Add a ConfigCategoryDescription element
 *
 * @param  elem    The ConfigCategoryDescription elemen to add
 */
void ConfigCategories::addCategoryDescription(ConfigCategoryDescription* elem)
{
	m_categories.push_back(elem);
}

/**
 * Return the JSON string of a ConfigCategoryDescription element
 */
string ConfigCategoryDescription::toJSON() const
{
	ostringstream convert;

	convert << "{\"key\": \"" << m_name << "\", ";
	convert << "\"description\" : \"" << m_description << "\"}";

	return convert.str();
}

/**
 * Return the JSON string of all ConfigCategoryDescription
 * elements in m_categories
 */
string ConfigCategories::toJSON() const
{
	ostringstream convert;

	convert << "[";
	for (auto it = m_categories.cbegin(); it != m_categories.cend(); it++)
	{
		convert << (*it)->toJSON();
		if (it + 1 != m_categories.cend() )
		{
                        convert << ", ";
		}
	}
	convert << "]";

	return convert.str();
}

/**
 * Configuration Category constructor
 *
 * @param name	The name of the configuration category
 * @param json	JSON content of the configuration category
 */
ConfigCategory::ConfigCategory(const string& name, const string& json) : m_name(name)
{
	Document doc;
	doc.Parse(json.c_str());
	if (doc.HasParseError())
	{
		Logger::getLogger()->error("Configuration parse error in category '%s', %s: %s at %d",
			name.c_str(), json.c_str(),
			GetParseError_En(doc.GetParseError()), (unsigned)doc.GetErrorOffset());
		throw new ConfigMalformed();
	}
	
	for (Value::ConstMemberIterator itr = doc.MemberBegin(); itr != doc.MemberEnd(); ++itr)
	{
		try
		{
			m_items.push_back(new CategoryItem(itr->name.GetString(), itr->value));
		}
		catch (exception* e)
		{
			Logger::getLogger()->error("Configuration parse error in category '%s' item '%s', %s: %s",
				name.c_str(),
				itr->name.GetString(),
				json.c_str(),
				e->what());
			delete e;
			throw ConfigMalformed();
		}
		catch (...)
		{
			throw;
		}
	}
}

/**
 * Copy constructor for a configuration category
 */
ConfigCategory::ConfigCategory(ConfigCategory const& rhs)
{
	m_name = rhs.m_name;
	m_description = rhs.m_description;

	for (auto it = rhs.m_items.cbegin(); it != rhs.m_items.cend(); it++)
	{
		m_items.push_back(new CategoryItem(**it));
	}
}

/**
 * Configuration category destructor
 */
ConfigCategory::~ConfigCategory()
{
	for (auto it = m_items.cbegin(); it != m_items.cend(); it++)
	{
		delete *it;
	}
}

/**
 * Operator= for ConfigCategory
 */
ConfigCategory& ConfigCategory::operator=(ConfigCategory const& rhs)
{
	m_name = rhs.m_name;
	m_description = rhs.m_description;

	for (auto it = rhs.m_items.cbegin(); it != rhs.m_items.cend(); it++)
	{
		m_items.push_back(new CategoryItem(**it));
	}
	return *this;
}

/**
 * Set the m_value from m_default for each item
 */
void ConfigCategory::setItemsValueFromDefault()
{
	for (auto it = m_items.cbegin(); it != m_items.cend(); it++)
	{
		(*it)->m_value = string((*it)->m_default);
	}
}

/**
 * Check whether at least one item in the category object
 * has both 'value' and 'default' set.
 *
 * @throws ConfigValueFoundWithDefault
 */
void ConfigCategory::checkDefaultValuesOnly() const
{
	for (auto it = m_items.cbegin(); it != m_items.cend(); it++)
	{
		if (!(*it)->m_value.empty())
		{
			throw new ConfigValueFoundWithDefault((*it)->m_name);
		}
	}
}

/**
 * Add an item to a configuration category
 */
void ConfigCategory::addItem(const std::string& name, const std::string description,
                             const std::string& type, const std::string def,
                             const std::string& value)
{
	m_items.push_back(new CategoryItem(name, description, type, def, value));
}


/**
 * Check for the existance of an item within the configuration category
 *
 * @param name	Item name to check within the category
 */
bool ConfigCategory::itemExists(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return true;
		}
	}
	return false;
}

/**
 * Return the value of the configuration category item
 *
 * @param name	The name of the configuration item to return
 * @return string	The configuration item name
 * @throws exception if the item does not exist in the category
 */
string ConfigCategory::getValue(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return m_items[i]->m_value;
		}
	}
	throw new ConfigItemNotFound();
}

/**
 * Return the type of the configuration category item
 *
 * @param name	The name of the configuration item to return
 * @return string	The configuration item name
 * @throws exception if the item does not exist in the category
 */
string ConfigCategory::getType(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return m_items[i]->m_type;
		}
	}
	throw new ConfigItemNotFound();
}

/**
 * Return the description of the configuration category item
 *
 * @param name	The name of the configuration item to return
 * @return string	The configuration item name
 * @throws exception if the item does not exist in the category
 */
string ConfigCategory::getDescription(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return m_items[i]->m_description;
		}
	}
	throw new ConfigItemNotFound();
}

/**
 * Return the default value of the configuration category item
 *
 * @param name	The name of the configuration item to return
 * @return string	The configuration item name
 * @throws exception if the item does not exist in the category
 */
string ConfigCategory::getDefault(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return m_items[i]->m_default;
		}
	}
	throw new ConfigItemNotFound();
}

/**
 * Return if the configuration item is a string item
 *
 * @param name		The name of the item to test
 * @return bool		True if the item is a string type
 * @throws exception	If the item was not found in the configuration category
 */
bool ConfigCategory::isString(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return m_items[i]->m_itemType == CategoryItem::StringItem;
		}
	}
	throw new ConfigItemNotFound();
}

/**
 * Return if the configuration item is a JSON item
 *
 * @param name		The name of the item to test
 * @return bool		True if the item is a JSON type
 * @throws exception	If the item was not found in the configuration category
 */
bool ConfigCategory::isJSON(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return m_items[i]->m_itemType == CategoryItem::JsonItem;
		}
	}
	throw new ConfigItemNotFound();
}

/**
 * Return if the configuration item is a Bool item
 *
 * @param name		The name of the item to test
 * @return bool		True if the item is a Bool type
 * @throws exception	If the item was not found in the configuration category
 */
bool ConfigCategory::isBool(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return m_items[i]->m_itemType == CategoryItem::BoolItem;
		}
	}
	throw new ConfigItemNotFound();
}

/**
 * Return if the configuration item is a Numeric item
 *
 * @param name		The name of the item to test
 * @return bool		True if the item is a Numeric type
 * @throws exception	If the item was not found in the configuration category
 */
bool ConfigCategory::isNumber(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return m_items[i]->m_itemType == CategoryItem::NumberItem;
		}
	}
	throw new ConfigItemNotFound();
}

/**
 * Return if the configuration item is a Double item
 *
 * @param name		The name of the item to test
 * @return bool		True if the item is a Double type
 * @throws exception	If the item was not found in the configuration category
 */
bool ConfigCategory::isDouble(const string& name) const
{
	for (unsigned int i = 0; i < m_items.size(); i++)
	{
		if (name.compare(m_items[i]->m_name) == 0)
		{
			return m_items[i]->m_itemType == CategoryItem::DoubleItem;
		}
	}
	throw new ConfigItemNotFound();
}

/**
 * Set the description for the configuration category
 *
 * @param description	The configuration category description
 */
void ConfigCategory::setDescription(const string& description)
{
	m_description = description;
}

/**
 * Return JSON string of all category components
 */
string ConfigCategory::toJSON() const
{
ostringstream convert;

	convert << "{ \"key\" : \"" << m_name << "\", ";
	convert << "\"description\" : \"" << m_description << "\", \"value\" : ";
	// Add items
	convert << ConfigCategory::itemsToJSON();
	convert << " }";

	return convert.str();
}

/**
 * Return JSON string of category items only
 */
string ConfigCategory::itemsToJSON() const
{
ostringstream convert;

	convert << "{";
	for (auto it = m_items.cbegin(); it != m_items.cend(); it++)
	{
		convert << (*it)->toJSON();
		if (it + 1 != m_items.cend() )
		{
			convert << ", ";
		}
	}
	convert << "}";

	return convert.str();
}

/**
 * Constructor for a configuration item
 * @param name	The category item name
 * @param item	The item object to add
 * @throw	ConfigMalformed exception
 * @throw	runtime_error exception
 */
ConfigCategory::CategoryItem::CategoryItem(const string& name,
					   const Value& item)
{
	m_name = name;
	if (! item.IsObject())
	{
		throw new ConfigMalformed();
	}
	if (item.HasMember("type"))
	{
		m_type = item["type"].GetString();
	}
	else
	{
		m_type = "";
	}

	if (item.HasMember("description"))
	{
		m_description = item["description"].GetString();
	}
	else
	{
		m_description = "";
	}

	if (item.HasMember("order"))
	{
		m_order = item["order"].GetString();
	}
	else
	{
		m_order = "";
	}

	if (item.HasMember("readonly"))
	{
		m_readonly = item["readonly"].GetString();
	}
	else
	{
		m_readonly = "";
	}

	// Item "value" can be an escaped JSON string, so check m_type JSON as well
	if (item.HasMember("value") &&
	    ((item["value"].IsObject() || m_type.compare("JSON") == 0)))
	{
		rapidjson::StringBuffer strbuf;
		rapidjson::Writer<rapidjson::StringBuffer> writer(strbuf);
		item["value"].Accept(writer);
		m_value = item["value"].IsObject() ?
			  // use current string
			  strbuf.GetString() :
			  // Unescape the string
			  this->unescape(strbuf.GetString());

		// If it's not a real eject, check the string buffer it is:
		if (!item["value"].IsObject())
		{
			Document check;
			check.Parse(m_value.c_str());
			if (check.HasParseError())
			{
				throw new runtime_error(GetParseError_En(check.GetParseError()));
			}
			if (!check.IsObject())
			{
				throw new runtime_error("'value' JSON property is not an object");
			}
		}
		m_itemType = JsonItem;
	}
	// Item "value" is a Bool or m_type is boolean
	else if (item.HasMember("value") &&
		 (item["value"].IsBool() || m_type.compare("boolean") == 0))
	{
		m_value = !item["value"].IsBool() ?
			  // use string value
			  item["value"].GetString() :
			  // use bool value
			  item["value"].GetBool() ? "true" : "false";	
		
		m_itemType = BoolItem;
	}
	// Item "value" is just a string
	else if (item.HasMember("value") && item["value"].IsString())
	{
		m_value = item["value"].GetString();
		m_itemType = StringItem;
	}
	// Item "value" is a Double
	else if (item.HasMember("value") && item["value"].IsDouble())
	{
		rapidjson::StringBuffer strbuf;
		rapidjson::Writer<rapidjson::StringBuffer> writer(strbuf);
		item["value"].Accept(writer);
		m_value = strbuf.GetString();
		m_itemType = DoubleItem;
	}
	// Item "value" is a Number
	else if (item.HasMember("value") && item["value"].IsNumber())
	{
		// Don't check Uint/Int/Long etc: just get the string value
		rapidjson::StringBuffer strbuf;
		rapidjson::Writer<rapidjson::StringBuffer> writer(strbuf);
		item["value"].Accept(writer);
		m_value = strbuf.GetString();
		m_itemType = NumberItem;
	}
	// Item "value" has an unknwon type so far: set empty string
	else
	{
		m_value = "";
	}

	// Item "default" can be an escaped JSON string, so check m_type JSON as well
	if (item.HasMember("default") &&
	    ((item["default"].IsObject() || m_type.compare("JSON") == 0)))
	{
		rapidjson::StringBuffer strbuf;
		rapidjson::Writer<rapidjson::StringBuffer> writer(strbuf);
		item["default"].Accept(writer);
		m_default = item["default"].IsObject() ?
			  // use current string
			  strbuf.GetString() :
			  // Unescape the string
			  this->unescape(strbuf.GetString());

		// If it's not a real eject, check the string buffer it is:
		if (!item["default"].IsObject())
		{
			Document check;
			check.Parse(m_default.c_str());
			if (check.HasParseError())
			{
				throw new runtime_error(GetParseError_En(check.GetParseError()));
			}
			if (!check.IsObject())
			{
				throw new runtime_error("'default' JSON property is not an object");
			}
		}
		m_itemType = JsonItem;
	}
	// Item "default" is a Bool or m_type is boolean
	else if (item.HasMember("default") &&
		 (item["default"].IsBool() || m_type.compare("boolean") == 0))
	{
		m_default = !item["default"].IsBool() ?
			    // use string value
			    item["default"].GetString() :
			    // use bool value
			    item["default"].GetBool() ? "true" : "false";	
		
		m_itemType = BoolItem;
	}
	// Item "default" is just a string
	else if (item.HasMember("default") && item["default"].IsString())
	{
		m_default = item["default"].GetString();
		m_itemType = StringItem;
	}
	// Item "default" is a Double
	else if (item.HasMember("default") && item["default"].IsDouble())
	{
		rapidjson::StringBuffer strbuf;
		rapidjson::Writer<rapidjson::StringBuffer> writer(strbuf);
		item["default"].Accept(writer);
		m_default = strbuf.GetString();
		m_itemType = DoubleItem;
	}
	// Item "default" is a Number
	else if (item.HasMember("default") && item["default"].IsNumber())
	{
		// Don't check Uint/Int/Long etc: just get the string value
		rapidjson::StringBuffer strbuf;
		rapidjson::Writer<rapidjson::StringBuffer> writer(strbuf);
		item["default"].Accept(writer);
		m_default = strbuf.GetString();
		m_itemType = NumberItem;
	}
	else
	// Item "default" has an unknwon type so far: set empty string
	{
		m_default = "";
	}
}

/**
 * Constructor for a configuration item
 */
ConfigCategory::CategoryItem::CategoryItem(const string& name, const std::string& description,
                                           const std::string& type, const std::string def,
                                           const std::string& value)
{
	m_name = name;
	m_description = description;
	m_type = type;
	m_default = def;
	m_value = value;
	m_itemType = StringItem;
}

/**
 * Create a JSON representation of the configuration item
 */
string ConfigCategory::CategoryItem::toJSON() const
{
ostringstream convert;

	convert << "\"" << m_name << "\" : { ";
	convert << "\"description\" : \"" << m_description << "\", ";
	convert << "\"type\" : \"" << m_type << "\", ";

	if (m_itemType == StringItem ||
	    m_itemType == BoolItem)
	{
		convert << "\"value\" : \"" << m_value << "\", ";
		convert << "\"default\" : \"" << m_default << "\" }";
	}
	else if (m_itemType == JsonItem ||
		 m_itemType == NumberItem ||
		 m_itemType == DoubleItem)
	{
		convert << "\"value\" : " << m_value << ", ";
		convert << "\"default\" : " << m_default << " }";
	}
	return convert.str();
}

/**
 * Return only "default" item values
 */
string ConfigCategory::CategoryItem::defaultToJSON() const
{
ostringstream convert;

	convert << "\"" << m_name << "\" : { ";
	convert << "\"description\" : \"" << m_description << "\", ";
	convert << "\"type\" : \"" << m_type << "\", ";

	if (!m_order.empty())
	{
		convert << "\"order\" : \"" << m_order << "\", ";
	}

	if (!m_readonly.empty())
	{
		convert << "\"readonly\" : \"" << m_readonly << "\", ";
	}


	if (m_itemType == StringItem ||
	    m_itemType == BoolItem)
	{
		convert << "\"default\" : \"" << m_default << "\" }";
	}
	/**
	 * NOTE:
	 * These data types must be all escaped.
	 * "default" items in the DefaultConfigCategory class are sent to
	 * ConfigurationManager interface which requires string values only:
	 *
	 * examples:
	 * we must use "100" not 100
	 * and for JSON
	 * "{\"pipeline\":[\"scale\"]}" not {"pipeline":["scale"]}
	 */
	else if (m_itemType == JsonItem ||
		 m_itemType == NumberItem ||
		 m_itemType == DoubleItem)
	{
		convert << "\"default\" : \"" << escape(m_default) << "\" }";
	}
	return convert.str();
}

// DefaultConfigCategory constructor
DefaultConfigCategory::DefaultConfigCategory(const string& name, const string& json) :
                                            ConfigCategory::ConfigCategory(name, json)
{
}

/**
 * Return JSON string of all category components
 * of a DefaultConfigCategory class
 */
string DefaultConfigCategory::toJSON() const
{
ostringstream convert;

	convert << "{ ";
	convert << "\"key\" : \"" << m_name << "\", ";
	convert << "\"description\" : \"" << m_description << "\", \"value\" : ";
	// Add items
	convert << DefaultConfigCategory::itemsToJSON();
	convert << " }";

	return convert.str();
}

/**
 * Return DefaultConfigCategory "default" items only
 */
string DefaultConfigCategory::itemsToJSON() const
{
ostringstream convert;
        
	convert << "{";
	for (auto it = m_items.cbegin(); it != m_items.cend(); it++)
	{       
		convert << (*it)->defaultToJSON();
		if (it + 1 != m_items.cend() )
		{       
			convert << ", ";
		}
	}
	convert << "}";

	return convert.str();
}

std::string ConfigCategory::CategoryItem::escape(const std::string& subject) const
{
size_t pos = 0;
string replace("\\\"");
string escaped = subject;

	while ((pos = escaped.find("\"", pos)) != std::string::npos)
	{
		escaped.replace(pos, 1, replace);
		pos += replace.length();
	}
	return escaped;
}

/**
 * Return JSON string of a category item
 * @param itemName	The given item within current category
 * @return		The JSON string version of itemName
 *			If not found {} is returned
 */
string ConfigCategory::itemToJSON(const string& itemName) const
{
	ostringstream convert;
        
        convert << "{";
        for (auto it = m_items.cbegin(); it != m_items.cend(); it++)
        {
		if ((*it)->m_name.compare(itemName) == 0)
		{
                	convert << (*it)->toJSON();
		}
	}
	convert << "}";
        
	return convert.str();
}

/**
 * Return unescaped version of a JSON string
 *
 * Routine removes \" inside the string
 * and leading and trailing "
 *
 * @param subject	Input string
 * @return		Unescaped string
 */
std::string ConfigCategory::CategoryItem::unescape(const std::string& subject) const
{
	size_t pos = 0;
	string replace("");
	string json = subject;

	// Replace '\"' with '"'
        while ((pos = json.find("\\\"", pos)) != std::string::npos)
        {
                json.replace(pos, 1, "");
        }
	// Remove leading '"'
	if (json[0] == '\"')
	{
		json.erase(0, 1);
	}
	// Remove trainling '"'
	if (json[json.length() - 1] == '\"')
	{
		json.erase(json.length() - 1, 1);
	}
        return json;
}

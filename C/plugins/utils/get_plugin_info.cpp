/*
 * Utility to extract plugin_info from north/south C plugin library
 *
 * Copyright (c) 2018 Dianomic Systems
 *
 * Released under the Apache 2.0 Licence
 *
 * Author: Amandeep Singh Arora, Massimiliano Pinto
 */

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <dlfcn.h>
#include "plugin_api.h"
#include <string.h>
#include <string>

typedef PLUGIN_INFORMATION *(*func_t)();
typedef std::string *(*extra_config_t)();
typedef void *(*generic_t)();

/**
 * Extract value of a given symbol from given plugin library
 *
 *    Usage: get_plugin_info <plugin library> <function symbol to fetch plugin info from>
 *
 * @param argv[1]  relative/absolute path to north/south C plugin shared library
 *
 * @param argv[2]  symbol to extract value from (typically 'plugin_info')
 */
int main(int argc, char *argv[])
{
  void *hndl;

  if (argc<2)
  {
    fprintf(stderr, "Insufficient number of args...\n\nUsage: %s "
            "<plugin library> <function to fetch plugin info>\n",
            argv[0]);
    exit(1);
  }

  if (access(argv[1], F_OK|R_OK) != 0)
  {
    fprintf(stderr, "Unable to access library file '%s', exiting...\n",
            argv[1]);
    exit(2);
  }

  if ((hndl = dlopen(argv[1], RTLD_GLOBAL|RTLD_LAZY)) != NULL)
  {
    generic_t method = (generic_t)dlsym(hndl, argv[2]);
    if (method == NULL)
    {
      // Unable to find plugin_info entry point
      fprintf(stderr, "Plugin library %s does not support %s function : %s\n",
              argv[1],
              argv[2],
              dlerror());
      dlclose(hndl);
      exit(3);
    }
    if (strcmp(argv[2], "plugin_info") == 0)
    {
	func_t infoEntry = (func_t)method;
        PLUGIN_INFORMATION *info = (PLUGIN_INFORMATION *)(*infoEntry)();
        printf("{\"name\": \"%s\", \"version\": \"%s\", \"type\": \"%s\", "
               "\"interface\": \"%s\", \"config\": %s}\n",
               info->name,
               info->version,
               info->type,
               info->interface,
               info->config);
    }
    else if (strcmp(argv[2], "plugin_extra_config") == 0)
    {
       extra_config_t extraConfigEntry = (extra_config_t)method;	
       std::string* pluginData = (std::string *)(*extraConfigEntry)();
       if (pluginData == NULL ||
           pluginData->empty())
       {
          // Set empty JSON object
          pluginData = new std::string("{}");
       }
       printf("{ \"name\": \"Additional configuration\", "
              "\"description\": \"Additional configuration categories "
              "to pass to plugin_init\", \"categories\" : %s}\n",
              pluginData->c_str());
    }
    else
    {
        printf("Output data format doesn't exist for function '%s'\n", argv[2]);
    }
  }
  else
  {
    fprintf(stderr, "dlopen failed: %s\n", dlerror());
  }

  return 0;
}


===========================
Octavia Distributor API
===========================

Introduction
============
This document describes the API interface between the reference
distributor driver and its corresponding distributor module.

Octavia reference distributor uses a web service API for configuration and
control. This API should be secured through the use of TLS encryption as well
as bi-directional verification of client- and server-side certificates. (The
exact process for generating and distributing these certificates should be
covered in another document.)

In addition to the web service configuration and control interface, the
distributor may use an HMAC-signed UDP protocol for communicating regular,
less-vital information to the controller (ex. statistics updates and
health checks).
Information on this will also be covered in another document.


.. contents::

Versioning
----------
All Octavia APIs (including internal APIs like this one) are versioned. For the
purposes of this document, the initial version of this API shall be v0.1. (So,
any reference to a *:version* variable should be replaced with the literal
string 'v0.1'.)

Response codes
--------------
Typical response codes are:

* 200 OK - Operation was completed as requested.
* 201 Created - Operation successfully resulted in the creation / processing
  of a file.
* 202 Accepted - Command was accepted but is not completed. (Note that this is
  used for asynchronous processing.)
* 400 Bad Request - API handler was unable to complete request.
* 401 Unauthorized - Authentication of the client certificate failed.
* 404 Not Found - The requested file was not found.
* 500 Internal Server Error - Usually indicates a permissions problem

API
===

Get distributor info
--------------------
* **URL:** /info
* **Method:** GET
* **URL params:** none
* **Data params:** none
* **Success Response:**

  * Code: 200

    * Content: JSON formatted listing of several basic distributor data.

* **Error Response:**

  * none

JSON Response attributes:

* *hostname* - distributor hostname
* *api_version* - Version of distributor API in use

**Notes:** The data in this request is used by the controller for determining
the distributor and API version numbers.

It's also worth noting that this is the only API command that doesn't have a
version string prepended to it.

**Examples:**

* Success code 200:

::

  {
    'hostname': 'octavia-haproxy-img-00328.local',
    'api_version': '0.1',
  }

Get distributor diagnostics
---------------------------

* **URL:** /*:version*/diagnostics
* **Method:** GET
* **URL params:** none
* **Data params:** none
* **Success Response:**

  * Code: 200

    * Content: JSON formatted listing of various amphora statistics.

* **Error Response:**

  * none

JSON Response attributes:

* *hostname* - amphora hostname
* *api_version* - Version of API/agent in use
* *network_tx* - Current total outbound bandwidth in bytes/sec (30-second
  snapshot)
* *network_rx* - Current total inbound bandwidth in bytes/sec (30-second
  snapshot)
* *active* - is distributor role Active
* *cpu* - list of percent CPU usage broken down into:

  * total
  * user
  * system
  * soft_irq

* *memory* - memory usage in kilobytes broken down into:

  * total
  * free
  * available
  * buffers
  * cached
  * swap_used
  * shared
  * slab

* *disk* - disk usage in kilobytes for root filesystem, listed as:

  * used
  * available

* *load* - System load (list)
* *topology* - Current topology
* *topology_status* - Is topology status valid
* *packages* - list of load-balancing related packages installed with versions
  (eg. OpenSSL, haproxy, nginx, etc.)

**Notes:** The data in this request is meant to provide intelligence for an
auto-scaling orchestration controller (heat) in order to determine whether
additional (or fewer) virtual amphorae are necessary to handle load. As such,
we may add additional parameters to the JSON listing above if they prove to be
useful for making these decisions.

The data in this request is also used by the controller for determining overall
health of the amphora, currently-configured topology and role, etc.

**Examples**

* Success code 200:

::

  {
    'hostname': 'octavia-haproxy-img-00328.local',
    'api_version': '0.1',
    'networks': {
        'eth0': {
            'network_tx': 3300138,
            'network_rx': 982001, }}
    'cpu':{
      'total': 0.43,
      'user': 0.30,
      'system': 0.05,
      'soft_irq': 0.08,
    },
    'memory':{
      'total': 4087402,
      'free': 760656,
      'available': 2655901,
      'buffers': 90980,
      'cached': 1830143,
      'swap_used': 943,
      'shared': 105792,
      'slab': 158819,
      'committed_as': 2643480,
    },
    'disk':{
      'used': 1234567,
      'available': 5242880,
    },
    'load': [0.50, 0.45, 0.47],
    'packages':[
      {'bash': '4.3.23'},
      {'lighttpd': '1.4.33-1'},
      {'openssl': '1.0.1f'},
      <cut for brevity>
    ],
   }

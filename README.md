# OpenVMS

Miscellaneous scripts and data for OpenVMS.

For more details on these scripts see <https://wb8tyw-projects.blogspot.com/>

## kvm

Files for using OpenVMS x86_64 on KVM hosts.

### kvm/setup_vms_community_kvm.py

  This script uses libvirt to start the VM, and then do everything
  needed to get a system so that it can be accessed by either DECnet
  or SSH to complete the install.

### kvm/setup_vms_community_kvm_v922.py

  Older version that only got the system to the point where DECnet can
  access it.

### kvm/vms_kvm_template.xml

  This is a template generated from the dumping the XML that was created
  and modified by the virt-install and virt-manager tools.

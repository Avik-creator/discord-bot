#!/usr/bin/env python3
"""
Script to fix timeout issues in Discord bot commands
Adds defer() and changes response.send_message to followup.send
"""
import re
import sys

def fix_file(filepath):
    """Fix a single file"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # Find all async def functions that use AsyncSessionLocal
        # Pattern: async def function_name(self, interaction: discord.Interaction
        pattern = r'(async def (\w+)\(self, interaction: discord\.Interaction[^)]*\):)\s*("""[^"]*"""\s*)?(async with AsyncSessionLocal\(\) as session:)'
        
        def add_defer(match):
            func_def = match.group(1)
            func_name = match.group(2)
            docstring = match.group(3) or ""
            async_with = match.group(4)
            
            # Check if defer already exists
            if 'await interaction.response.defer' in original_content[original_content.find(match.group(0)):original_content.find(match.group(0))+500]:
                return match.group(0)
            
            return f'{func_def}\n        """{func_name}"""\n        await interaction.response.defer(ephemeral=False)\n        \n        try:\n            {async_with}'
        
        content = re.sub(pattern, add_defer, content, flags=re.MULTILINE)
        
        # Replace all response.send_message with followup.send (but only in functions that have defer)
        # This is a simple replacement - we'll do it carefully
        lines = content.split('\n')
        new_lines = []
        in_deferred_function = False
        
        for i, line in enumerate(lines):
            # Check if we're entering a function with defer
            if 'await interaction.response.defer' in line:
                in_deferred_function = True
                new_lines.append(line)
                continue
            
            # Check if we're leaving the function (next function definition or end of class)
            if re.match(r'\s*(async )?def \w+\(', line) and 'await interaction.response.defer' not in line:
                in_deferred_function = False
            
            # Replace response.send_message with followup.send in deferred functions
            if in_deferred_function and 'await interaction.response.send_message' in line:
                line = line.replace('await interaction.response.send_message', 'await interaction.followup.send')
            
            new_lines.append(line)
        
        content = '\n'.join(new_lines)
        
        if content != original_content:
            with open(filepath, 'w') as f:
                f.write(content)
            print(f"✅ Fixed {filepath}")
            return True
        else:
            print(f"⏭️  No changes needed in {filepath}")
            return False
            
    except Exception as e:
        print(f"❌ Error fixing {filepath}: {e}")
        return False

if __name__ == "__main__":
    files = ['cogs/team.py', 'cogs/match.py', 'cogs/admin.py', 'cogs/server_config.py']
    
    for filepath in files:
        fix_file(filepath)
    
    print("\n✅ Done! Please review the changes and test the bot.")

